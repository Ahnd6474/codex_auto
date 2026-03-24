from __future__ import annotations

import subprocess
from pathlib import Path

from .codex_runner import CodexRunner
from .git_ops import GitOps
from .memory import MemoryStore
from .models import CandidateTask, ProjectContext, RuntimeOptions, TestRunResult
from .planning import (
    attempt_history_entry,
    build_mid_term_plan,
    candidate_tasks_from_mid_term,
    ensure_scope_guard,
    generate_long_term_plan,
    implementation_prompt,
    reflection_markdown,
    scan_repository_inputs,
    select_candidate,
    validate_mid_term_subset,
    write_active_task,
)
from .reporting import Reporter
from .utils import now_utc_iso, read_text, write_text
from .workspace import WorkspaceManager


class Orchestrator:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace = WorkspaceManager(workspace_root)
        self.git = GitOps()

    def init_repo(
        self,
        repo_url: str,
        branch: str,
        runtime: RuntimeOptions,
        long_term_plan_path: Path | None = None,
    ) -> ProjectContext:
        context = self.workspace.initialize_project(repo_url=repo_url, branch=branch, runtime=runtime)
        try:
            self.git.clone_or_update(repo_url, branch, context.paths.repo_dir)
            self.git.configure_local_identity(
                context.paths.repo_dir,
                runtime.git_user_name,
                runtime.git_user_email,
            )
            repo_inputs = scan_repository_inputs(context.paths.repo_dir)
            if long_term_plan_path:
                long_term_text = Path(long_term_plan_path).read_text(encoding="utf-8")
            elif context.paths.long_term_plan_file.exists():
                long_term_text = read_text(context.paths.long_term_plan_file)
            else:
                long_term_text = generate_long_term_plan(context, repo_inputs)
            write_text(context.paths.long_term_plan_file, long_term_text)
            write_text(context.paths.scope_guard_file, ensure_scope_guard(context))
            mid_term_text, _ = build_mid_term_plan(long_term_text)
            write_text(context.paths.mid_term_plan_file, mid_term_text)

            for file_path, starter in [
                (context.paths.active_task_file, "# Active Task\n\nNo active task selected yet.\n"),
                (context.paths.block_review_file, "# Block Review\n\nNo completed blocks yet.\n"),
                (context.paths.research_notes_file, "# Research Notes\n\nNo research notes recorded yet.\n"),
                (context.paths.attempt_history_file, "# Attempt History\n\n"),
            ]:
                if not file_path.exists():
                    write_text(file_path, starter)

            safe_revision = self.git.current_revision(context.paths.repo_dir)
            context.metadata.current_safe_revision = safe_revision
            context.metadata.last_run_at = now_utc_iso()
            context.metadata.current_status = "ready"
            context.loop_state.current_safe_revision = safe_revision
            self.workspace.save_project(context)
            return context
        except Exception as exc:
            context.metadata.last_run_at = now_utc_iso()
            context.metadata.current_status = "init_failed"
            write_text(context.paths.reports_dir / "init_error.txt", str(exc).strip() + "\n")
            self.workspace.save_project(context)
            raise

    def run(
        self,
        repo_url: str,
        branch: str,
        runtime: RuntimeOptions,
        long_term_plan_path: Path | None = None,
        resume: bool = False,
    ) -> ProjectContext:
        existing = self.workspace.find_project(repo_url, branch)
        if existing is None:
            context = self.init_repo(repo_url, branch, runtime, long_term_plan_path=long_term_plan_path)
        else:
            context = existing
            context.runtime = runtime
            self.git.clone_or_update(repo_url, branch, context.paths.repo_dir)
            self.git.configure_local_identity(
                context.paths.repo_dir,
                runtime.git_user_name,
                runtime.git_user_email,
            )
            if not resume and long_term_plan_path:
                write_text(context.paths.long_term_plan_file, Path(long_term_plan_path).read_text(encoding="utf-8"))

        self.workspace.save_project(context)
        runner = CodexRunner(context.runtime.codex_path)
        memory = MemoryStore(context.paths)
        reporter = Reporter(context)

        block_limit = max(1, context.runtime.max_blocks)
        for _ in range(block_limit):
            stop_reason = self._stop_reason(context)
            if stop_reason:
                context.loop_state.stop_reason = stop_reason
                break
            self._run_single_block(context, runner, memory, reporter)
            self.workspace.save_project(context)
            if context.loop_state.stop_reason:
                break

        reporter.write_status_report()
        self.workspace.save_project(context)
        return context

    def resume(self, repo_url: str, branch: str, runtime: RuntimeOptions) -> ProjectContext:
        return self.run(repo_url=repo_url, branch=branch, runtime=runtime, resume=True)

    def list_projects(self) -> list[ProjectContext]:
        return self.workspace.list_projects()

    def status(self, repo_url: str, branch: str) -> ProjectContext:
        context = self.workspace.find_project(repo_url, branch)
        if context is None:
            raise KeyError(f"Repository {repo_url} [{branch}] is not managed in this workspace.")
        return context

    def history(self, repo_url: str, branch: str, limit: int = 10) -> str:
        context = self.status(repo_url, branch)
        return Reporter(context).render_history(limit=limit)

    def report(self, repo_url: str, branch: str) -> Path:
        context = self.status(repo_url, branch)
        return Reporter(context).write_status_report()

    def _run_single_block(
        self,
        context: ProjectContext,
        runner: CodexRunner,
        memory: MemoryStore,
        reporter: Reporter,
    ) -> None:
        context.loop_state.block_index += 1
        block_index = context.loop_state.block_index
        context.metadata.current_status = f"running:block:{block_index}"
        context.metadata.last_run_at = now_utc_iso()
        safe_revision = context.metadata.current_safe_revision or self.git.current_revision(context.paths.repo_dir)

        long_term_text = read_text(context.paths.long_term_plan_file)
        mid_term_text, mid_items = build_mid_term_plan(long_term_text)
        valid_subset, violations = validate_mid_term_subset(mid_term_text, long_term_text)
        if not valid_subset:
            raise RuntimeError(f"Mid-term plan violated long-term scope: {violations}")
        write_text(context.paths.mid_term_plan_file, mid_term_text)

        memory_context = memory.render_context(mid_term_text)
        candidates = candidate_tasks_from_mid_term(mid_items, memory_context)
        selected = select_candidate(candidates)
        context.loop_state.current_task = selected.title
        context.loop_state.last_candidates = [candidate.to_dict() for candidate in candidates]
        write_active_task(context, selected, memory_context)

        block_commit_hashes: list[str] = []
        block_changed_files: list[str] = []
        selected_task = selected.title

        for pass_name in ["block-a-pass-1", "block-a-pass-2"]:
            pass_result, test_result, commit_hash = self._execute_pass(
                context=context,
                runner=runner,
                reporter=reporter,
                block_index=block_index,
                candidate=selected,
                pass_name=pass_name,
                safe_revision=safe_revision,
                search_enabled=False,
                memory_context_override=memory_context,
            )
            block_changed_files.extend(pass_result.changed_files)
            if test_result is None:
                context.loop_state.counters.regression_failures += 1
                context.loop_state.stop_reason = self._stop_reason(context)
                memory.record_failure(
                    task=selected_task,
                    summary=f"{pass_name} failed. Changes rolled back to {safe_revision}.",
                    tags=["implementation", "regression"],
                    block_index=block_index,
                    commit_hash=None,
                )
                reporter.write_block_review(
                    reflection_markdown(selected_task, "Implementation pass failed; rolled back.", [], [])
                )
                reporter.append_attempt_history(
                    attempt_history_entry(block_index, selected_task, "rolled back after regression", [])
                )
                reporter.log_block(
                    {
                        "repository_id": context.metadata.repo_id,
                        "repository_slug": context.metadata.slug,
                        "block_index": block_index,
                        "status": "rolled_back",
                        "selected_task": selected_task,
                        "changed_files": [],
                        "test_summary": "regression failure",
                        "commit_hashes": [],
                        "rollback_status": "rolled_back_to_safe_revision",
                    }
                )
                return
            if commit_hash:
                block_commit_hashes.append(commit_hash)
                context.metadata.current_safe_revision = commit_hash
                context.loop_state.current_safe_revision = commit_hash
                safe_revision = commit_hash

        research_memory = memory.render_context(selected_task)
        research_pass, research_tests, research_commit = self._execute_pass(
            context=context,
            runner=runner,
            reporter=reporter,
            block_index=block_index,
            candidate=selected,
            pass_name="block-b-research-pass",
            safe_revision=safe_revision,
            search_enabled=True,
            memory_context_override=research_memory,
        )
        block_changed_files.extend(research_pass.changed_files)
        if research_tests is None:
            context.loop_state.counters.regression_failures += 1
            context.loop_state.stop_reason = self._stop_reason(context)
            memory.record_failure(
                task=selected_task,
                summary="Research-backed pass regressed tests and was rolled back.",
                tags=["research", "regression"],
                block_index=block_index,
                commit_hash=None,
            )
            reporter.write_block_review(
                reflection_markdown(selected_task, "Research-backed pass failed; rolled back.", [], block_commit_hashes)
            )
            reporter.append_attempt_history(
                attempt_history_entry(block_index, selected_task, "research pass rolled back", block_commit_hashes)
            )
            reporter.log_block(
                {
                    "repository_id": context.metadata.repo_id,
                    "repository_slug": context.metadata.slug,
                    "block_index": block_index,
                    "status": "partial_success_then_rollback",
                    "selected_task": selected_task,
                    "changed_files": sorted(set(block_changed_files)),
                    "test_summary": "research regression failure",
                    "commit_hashes": block_commit_hashes,
                    "rollback_status": "rolled_back_to_safe_revision",
                }
            )
            return
        if research_commit:
            block_commit_hashes.append(research_commit)
            context.metadata.current_safe_revision = research_commit
            context.loop_state.current_safe_revision = research_commit

        if context.runtime.allow_push and block_commit_hashes:
            self.git.push(context.paths.repo_dir, context.metadata.branch)

        made_progress = bool(block_commit_hashes)
        if made_progress:
            context.loop_state.counters.no_progress_blocks = 0
            context.loop_state.counters.empty_cycles = 0
        else:
            context.loop_state.counters.no_progress_blocks += 1
            context.loop_state.counters.empty_cycles += 1

        test_summary = research_tests.summary if research_tests else "No research-backed test run."
        reporter.write_block_review(
            reflection_markdown(selected_task, test_summary, sorted(set(block_changed_files)), block_commit_hashes)
        )
        reporter.append_attempt_history(
            attempt_history_entry(
                block_index,
                selected_task,
                "completed" if made_progress else "completed with no committed changes",
                block_commit_hashes,
            )
        )
        memory.record_task_summary(
            task=selected_task,
            summary=test_summary,
            tags=["task-summary"],
            block_index=block_index,
            commit_hash=block_commit_hashes[-1] if block_commit_hashes else None,
        )
        if made_progress:
            memory.record_success(
                task=selected_task,
                summary=f"Completed block with {len(block_commit_hashes)} safe commit(s).",
                tags=["implementation", "research"],
                block_index=block_index,
                commit_hash=block_commit_hashes[-1],
            )
        reporter.log_block(
            {
                "repository_id": context.metadata.repo_id,
                "repository_slug": context.metadata.slug,
                "block_index": block_index,
                "status": "completed",
                "selected_task": selected_task,
                "changed_files": sorted(set(block_changed_files)),
                "test_summary": test_summary,
                "commit_hashes": block_commit_hashes,
                "rollback_status": "not_needed",
            }
        )
        context.loop_state.last_commit_hash = block_commit_hashes[-1] if block_commit_hashes else context.loop_state.last_commit_hash
        context.loop_state.last_block_completed_at = now_utc_iso()
        context.metadata.current_status = "ready"
        context.loop_state.stop_reason = self._stop_reason(context)

    def _execute_pass(
        self,
        context: ProjectContext,
        runner: CodexRunner,
        reporter: Reporter,
        block_index: int,
        candidate: CandidateTask,
        pass_name: str,
        safe_revision: str,
        search_enabled: bool,
        memory_context_override: str | None = None,
    ) -> tuple:
        memory_context = memory_context_override or "No additional memory context."
        prompt = implementation_prompt(
            context=context,
            candidate=candidate,
            memory_context=memory_context,
            pass_name=pass_name,
            use_research=search_enabled,
        )
        run_result = runner.run_pass(
            context=context,
            prompt=prompt,
            pass_type=pass_name,
            block_index=block_index,
            search_enabled=search_enabled,
        )
        run_result.changed_files = self.git.changed_files(context.paths.repo_dir)
        if run_result.returncode != 0:
            self.git.hard_reset(context.paths.repo_dir, safe_revision)
            reporter.log_pass(
                {
                    "repository_id": context.metadata.repo_id,
                    "repository_slug": context.metadata.slug,
                    "block_index": block_index,
                    "pass_type": pass_name,
                    "selected_task": candidate.title,
                    "changed_files": run_result.changed_files,
                    "test_results": None,
                    "codex_return_code": run_result.returncode,
                    "commit_hash": None,
                    "rollback_status": "rolled_back_to_safe_revision",
                    "search_enabled": search_enabled,
                }
            )
            return run_result, None, None

        test_result = self._run_test_command(context, block_index, pass_name)
        reporter.save_test_result(block_index, pass_name, test_result)
        commit_hash: str | None = None
        rollback_status = "not_needed"
        if test_result.returncode != 0:
            self.git.hard_reset(context.paths.repo_dir, safe_revision)
            rollback_status = "rolled_back_to_safe_revision"
            test_result = None
        elif self.git.has_changes(context.paths.repo_dir):
            commit_hash = self.git.commit_all(
                context.paths.repo_dir,
                self._commit_message(block_index, pass_name, candidate.title),
            )
        reporter.log_pass(
            {
                "repository_id": context.metadata.repo_id,
                "repository_slug": context.metadata.slug,
                "block_index": block_index,
                "pass_type": pass_name,
                "selected_task": candidate.title,
                "changed_files": run_result.changed_files,
                "test_results": test_result.to_dict() if test_result else None,
                "codex_return_code": run_result.returncode,
                "commit_hash": commit_hash,
                "rollback_status": rollback_status,
                "search_enabled": search_enabled,
            }
        )
        return run_result, test_result, commit_hash

    def _run_test_command(self, context: ProjectContext, block_index: int, label: str) -> TestRunResult:
        block_dir = context.paths.logs_dir / f"block_{block_index:04d}"
        stdout_file = block_dir / f"{label}.test.stdout.log"
        stderr_file = block_dir / f"{label}.test.stderr.log"
        completed = subprocess.run(
            context.runtime.test_cmd,
            cwd=context.paths.repo_dir,
            shell=True,
            text=True,
            capture_output=True,
            check=False,
        )
        write_text(stdout_file, completed.stdout)
        write_text(stderr_file, completed.stderr)
        return TestRunResult(
            command=context.runtime.test_cmd,
            returncode=completed.returncode,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            summary=f"{context.runtime.test_cmd} exited with {completed.returncode}",
        )

    def _commit_message(self, block_index: int, pass_name: str, task: str) -> str:
        safe_task = " ".join(task.split())[:72]
        return f"codex-auto(block {block_index} {pass_name}): {safe_task}"

    def _stop_reason(self, context: ProjectContext) -> str | None:
        counters = context.loop_state.counters
        if counters.no_progress_blocks >= context.runtime.no_progress_limit:
            return f"no progress for {counters.no_progress_blocks} block(s)"
        if counters.regression_failures >= context.runtime.regression_limit:
            return f"repeated regression failures: {counters.regression_failures}"
        if counters.empty_cycles >= context.runtime.empty_cycle_limit:
            return f"too many empty cycles: {counters.empty_cycles}"
        return None
