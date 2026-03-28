from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
from uuid import uuid4

from .bridge_events import emit_bridge_event
from .models import LoopCounters, LoopState, ProjectContext, ProjectPaths, RepoMetadata, RuntimeOptions
from .parallel_resources import normalize_parallel_worker_mode
from .utils import ensure_dir, now_utc_iso, read_json, remove_tree, stable_repo_identity, write_json

LOCAL_PROJECT_LOG_DIRNAME = "jakal-flow-logs"


class WorkspaceManager:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.projects_root = self.workspace_root / "projects"
        self.history_root = self.workspace_root / "history"

    @property
    def registry_file(self) -> Path:
        return self.workspace_root / "registry.json"

    def _empty_registry(self) -> dict[str, dict[str, dict[str, str]]]:
        return {"projects": {}, "history": {}}

    def _read_registry(self) -> dict[str, dict[str, dict[str, str]]]:
        raw = read_json(self.registry_file, default=self._empty_registry())
        if not isinstance(raw, dict):
            return self._empty_registry()
        projects = raw.get("projects", {})
        history = raw.get("history", {})
        return {
            "projects": projects if isinstance(projects, dict) else {},
            "history": history if isinstance(history, dict) else {},
        }

    def _write_registry(self, registry: dict[str, dict[str, dict[str, str]]]) -> None:
        write_json(
            self.registry_file,
            {
                "projects": registry.get("projects", {}),
                "history": registry.get("history", {}),
            },
        )

    def ensure_workspace(self) -> None:
        ensure_dir(self.projects_root)
        ensure_dir(self.history_root)
        if not self.registry_file.exists():
            self._write_registry(self._empty_registry())
            return
        registry = self._read_registry()
        if read_json(self.registry_file, default=None) != registry:
            self._write_registry(registry)

    def build_paths(self, slug: str) -> ProjectPaths:
        return self.build_paths_from_root(self.projects_root / slug)

    def _apply_local_repo_log_paths(self, paths: ProjectPaths, repo_dir: Path) -> ProjectPaths:
        repo_logs_dir = repo_dir.resolve() / LOCAL_PROJECT_LOG_DIRNAME
        paths.logs_dir = repo_logs_dir
        paths.pass_log_file = repo_logs_dir / "passes.jsonl"
        paths.block_log_file = repo_logs_dir / "blocks.jsonl"
        paths.ui_event_log_file = repo_logs_dir / "ui_events.jsonl"
        return paths

    def build_paths_from_root(self, project_root: Path) -> ProjectPaths:
        resolved_root = project_root.resolve()
        docs_dir = resolved_root / "docs"
        memory_dir = resolved_root / "memory"
        logs_dir = resolved_root / "logs"
        reports_dir = resolved_root / "reports"
        state_dir = resolved_root / "state"
        return ProjectPaths(
            workspace_root=self.workspace_root,
            projects_root=self.projects_root,
            project_root=resolved_root,
            repo_dir=resolved_root / "repo",
            docs_dir=docs_dir,
            memory_dir=memory_dir,
            logs_dir=logs_dir,
            reports_dir=reports_dir,
            state_dir=state_dir,
            metadata_file=resolved_root / "metadata.json",
            project_config_file=resolved_root / "project_config.json",
            loop_state_file=state_dir / "LOOP_STATE.json",
            plan_file=docs_dir / "PLAN.md",
            mid_term_plan_file=docs_dir / "MID_TERM_PLAN.md",
            scope_guard_file=docs_dir / "SCOPE_GUARD.md",
            active_task_file=docs_dir / "ACTIVE_TASK.md",
            block_review_file=docs_dir / "BLOCK_REVIEW.md",
            checkpoint_timeline_file=docs_dir / "CHECKPOINT_TIMELINE.md",
            research_notes_file=docs_dir / "RESEARCH_NOTES.md",
            attempt_history_file=docs_dir / "attempt_history.md",
            success_patterns_file=memory_dir / "success_patterns.jsonl",
            failure_patterns_file=memory_dir / "failure_patterns.jsonl",
            task_summaries_file=memory_dir / "task_summaries.jsonl",
            pass_log_file=logs_dir / "passes.jsonl",
            block_log_file=logs_dir / "blocks.jsonl",
            checkpoint_state_file=state_dir / "CHECKPOINTS.json",
            execution_plan_file=state_dir / "EXECUTION_PLAN.json",
            lineage_state_file=state_dir / "LINEAGES.json",
            ml_mode_state_file=state_dir / "ML_MODE_STATE.json",
            ml_step_report_file=state_dir / "ML_STEP_REPORT.json",
            ml_experiment_reports_dir=state_dir / "ml_experiments",
            ui_control_file=state_dir / "UI_RUN_CONTROL.json",
            ui_event_log_file=logs_dir / "ui_events.jsonl",
            execution_flow_svg_file=docs_dir / "EXECUTION_FLOW.svg",
            closeout_report_file=docs_dir / "CLOSEOUT_REPORT.md",
            closeout_report_docx_file=reports_dir / "CLOSEOUT_REPORT.docx",
            ml_experiment_report_file=docs_dir / "ML_EXPERIMENT_REPORT.md",
            ml_experiment_results_svg_file=docs_dir / "ML_EXPERIMENT_RESULTS.svg",
        )

    def initialize_project(
        self,
        repo_url: str,
        branch: str,
        runtime: RuntimeOptions,
    ) -> ProjectContext:
        self.ensure_workspace()
        repo_id, slug = stable_repo_identity(repo_url, branch)
        paths = self.build_paths(slug)
        for directory in [
            paths.project_root,
            paths.repo_dir,
            paths.docs_dir,
            paths.memory_dir,
            paths.logs_dir,
            paths.reports_dir,
            paths.state_dir,
            paths.ml_experiment_reports_dir,
        ]:
            ensure_dir(directory)

        registry = self._read_registry()
        if repo_id in registry["projects"]:
            context = self.load_project_by_id(repo_id)
            context.runtime = runtime
            self.save_project(context)
            return context

        created_at = now_utc_iso()
        metadata = RepoMetadata(
            repo_id=repo_id,
            slug=slug,
            repo_url=repo_url,
            branch=branch,
            project_root=paths.project_root,
            repo_path=paths.repo_dir,
            created_at=created_at,
            display_name=slug,
        )
        loop_state = LoopState(repo_id=repo_id, repo_slug=slug)
        registry["projects"][repo_id] = {
            "repo_id": repo_id,
            "slug": slug,
            "repo_url": repo_url,
            "branch": branch,
            "project_root": str(paths.project_root),
            "repo_kind": "remote",
            "repo_path": str(paths.repo_dir),
        }
        self._write_registry(registry)
        self.save_project(ProjectContext(metadata=metadata, runtime=runtime, paths=paths, loop_state=loop_state))
        return self.load_project_by_id(repo_id)

    def initialize_local_project(
        self,
        project_dir: Path,
        branch: str,
        runtime: RuntimeOptions,
        origin_url: str = "",
        display_name: str = "",
    ) -> ProjectContext:
        self.ensure_workspace()
        resolved_dir = project_dir.resolve()
        repo_id, slug = stable_repo_identity(str(resolved_dir), branch)
        paths = self.build_paths(slug)
        paths.repo_dir = resolved_dir
        paths = self._apply_local_repo_log_paths(paths, resolved_dir)
        for directory in [
            paths.project_root,
            paths.docs_dir,
            paths.memory_dir,
            paths.logs_dir,
            paths.reports_dir,
            paths.state_dir,
            paths.ml_experiment_reports_dir,
        ]:
            ensure_dir(directory)
        ensure_dir(resolved_dir)

        registry = self._read_registry()
        if repo_id in registry["projects"]:
            context = self.load_project_by_id(repo_id)
            context.runtime = runtime
            context.metadata.repo_path = resolved_dir
            context.metadata.branch = branch
            context.metadata.repo_kind = "local"
            context.metadata.display_name = display_name.strip() or context.metadata.display_name or resolved_dir.name
            context.metadata.origin_url = origin_url or context.metadata.origin_url
            context.metadata.repo_url = origin_url or str(resolved_dir)
            context.paths.repo_dir = resolved_dir
            context.paths = self._apply_local_repo_log_paths(context.paths, resolved_dir)
            ensure_dir(context.paths.logs_dir)
            self.save_project(context)
            return context

        created_at = now_utc_iso()
        metadata = RepoMetadata(
            repo_id=repo_id,
            slug=slug,
            repo_url=origin_url or str(resolved_dir),
            branch=branch,
            project_root=paths.project_root,
            repo_path=resolved_dir,
            created_at=created_at,
            repo_kind="local",
            display_name=display_name.strip() or resolved_dir.name,
            origin_url=origin_url or None,
        )
        loop_state = LoopState(repo_id=repo_id, repo_slug=slug)
        registry["projects"][repo_id] = {
            "repo_id": repo_id,
            "slug": slug,
            "repo_url": metadata.repo_url,
            "branch": branch,
            "project_root": str(paths.project_root),
            "repo_kind": "local",
            "repo_path": str(resolved_dir),
        }
        self._write_registry(registry)
        self.save_project(ProjectContext(metadata=metadata, runtime=runtime, paths=paths, loop_state=loop_state))
        return self.load_project_by_id(repo_id)

    def _write_project_files(self, context: ProjectContext) -> None:
        write_json(context.paths.metadata_file, context.metadata.to_dict())
        write_json(context.paths.project_config_file, context.runtime.to_dict())
        write_json(context.paths.loop_state_file, context.loop_state.to_dict())

    def _managed_root_is_within(self, project_root: Path, expected_parent: Path) -> bool:
        resolved_root = project_root.resolve()
        resolved_parent = expected_parent.resolve()
        return resolved_root != resolved_parent and resolved_parent in resolved_root.parents

    def _rebind_context_root(self, context: ProjectContext, project_root: Path) -> ProjectContext:
        resolved_root = project_root.resolve()
        context.metadata.project_root = resolved_root
        context.paths = self.build_paths_from_root(resolved_root)
        if context.metadata.repo_kind == "local":
            context.paths.repo_dir = context.metadata.repo_path
            context.paths = self._apply_local_repo_log_paths(context.paths, context.metadata.repo_path)
        else:
            context.metadata.repo_path = context.paths.repo_dir
        return context

    def _remove_managed_project_root(self, project_root: Path, expected_parent: Path) -> None:
        resolved_root = project_root.resolve()
        if not self._managed_root_is_within(resolved_root, expected_parent):
            raise RuntimeError(f"Refusing to delete unexpected project root: {resolved_root}")
        remove_tree(resolved_root)

    def _active_registry_item(self, context: ProjectContext) -> dict[str, str]:
        return {
            "repo_id": context.metadata.repo_id,
            "slug": context.metadata.slug,
            "repo_url": context.metadata.repo_url,
            "branch": context.metadata.branch,
            "project_root": str(context.metadata.project_root),
            "repo_kind": context.metadata.repo_kind,
            "repo_path": str(context.metadata.repo_path),
        }

    def _history_registry_item(self, context: ProjectContext) -> dict[str, str]:
        return {
            "archive_id": str(context.metadata.archive_id or ""),
            "repo_id": context.metadata.repo_id,
            "source_repo_id": str(context.metadata.source_repo_id or context.metadata.repo_id),
            "slug": context.metadata.slug,
            "repo_url": context.metadata.repo_url,
            "branch": context.metadata.branch,
            "project_root": str(context.metadata.project_root),
            "repo_kind": context.metadata.repo_kind,
            "repo_path": str(context.metadata.repo_path),
            "archived_at": str(context.metadata.archived_at or ""),
            "display_name": str(context.metadata.display_name or context.metadata.slug),
        }

    def _should_emit_project_state_sync(self, context: ProjectContext) -> bool:
        status = str(context.metadata.current_status or "").strip().lower()
        current_task = str(context.loop_state.current_task or "").strip()
        return (
            status.startswith("running:")
            or bool(current_task)
            or bool(context.loop_state.pending_checkpoint_approval)
        )

    def _emit_project_state_sync(self, context: ProjectContext) -> None:
        if not self._should_emit_project_state_sync(context):
            return
        emit_bridge_event(
            "project.ui_event",
            {
                "repo_id": context.metadata.repo_id,
                "project_dir": str(context.metadata.repo_path),
                "project_status": str(context.metadata.current_status or "").strip(),
                "event": {
                    "timestamp": now_utc_iso(),
                    "event_type": "project-state-synced",
                    "message": "Project state updated during execution.",
                    "details": {
                        "current_task": str(context.loop_state.current_task or "").strip(),
                        "pending_checkpoint_approval": bool(context.loop_state.pending_checkpoint_approval),
                        "last_run_at": str(context.metadata.last_run_at or "").strip(),
                    },
                },
            },
        )

    def save_project(self, context: ProjectContext) -> None:
        self._write_project_files(context)
        registry = self._read_registry()
        if context.metadata.archived and context.metadata.archive_id:
            registry["history"][context.metadata.archive_id] = self._history_registry_item(context)
            self._write_registry(registry)
            self._emit_project_state_sync(context)
            return
        if context.metadata.repo_id in registry["projects"]:
            registry["projects"][context.metadata.repo_id] = self._active_registry_item(context)
            self._write_registry(registry)
        self._emit_project_state_sync(context)

    def load_project_by_id(self, repo_id: str) -> ProjectContext:
        registry = self._read_registry()
        item = registry["projects"].get(repo_id)
        if not item:
            raise KeyError(f"Unknown repository id: {repo_id}")
        return self.load_project_from_root(Path(item["project_root"]))

    def load_history_by_id(self, archive_id: str) -> ProjectContext:
        registry = self._read_registry()
        item = registry["history"].get(archive_id)
        if not item:
            raise KeyError(f"Unknown archive id: {archive_id}")
        context = self.load_project_from_root(Path(item["project_root"]))
        context.metadata.archived = True
        context.metadata.archive_id = archive_id
        context.metadata.archived_at = str(item.get("archived_at", "")).strip() or context.metadata.archived_at
        context.metadata.source_repo_id = str(item.get("source_repo_id", "")).strip() or context.metadata.source_repo_id
        return context

    def load_project_by_slug(self, slug: str) -> ProjectContext:
        return self.load_project_from_root(self.projects_root / slug)

    def load_project_from_root(self, project_root: Path) -> ProjectContext:
        paths = self.build_paths_from_root(project_root)
        metadata_data = read_json(paths.metadata_file)
        runtime_data = read_json(paths.project_config_file)
        loop_state_data = read_json(paths.loop_state_file)
        if not metadata_data or not runtime_data or not loop_state_data:
            raise FileNotFoundError(f"Project data is incomplete for root {project_root}")

        metadata = RepoMetadata(
            repo_id=metadata_data["repo_id"],
            slug=metadata_data["slug"],
            repo_url=metadata_data["repo_url"],
            branch=metadata_data["branch"],
            project_root=paths.project_root,
            repo_path=Path(metadata_data["repo_path"]),
            created_at=metadata_data["created_at"],
            last_run_at=metadata_data.get("last_run_at"),
            current_status=metadata_data.get("current_status", "initialized"),
            current_safe_revision=metadata_data.get("current_safe_revision"),
            repo_kind=metadata_data.get("repo_kind", "remote"),
            display_name=metadata_data.get("display_name"),
            origin_url=metadata_data.get("origin_url"),
            archived=bool(metadata_data.get("archived", False)),
            archive_id=metadata_data.get("archive_id"),
            archived_at=metadata_data.get("archived_at"),
            source_repo_id=metadata_data.get("source_repo_id"),
        )
        if metadata.repo_kind == "local":
            paths.repo_dir = metadata.repo_path
            paths = self._apply_local_repo_log_paths(paths, metadata.repo_path)
        else:
            metadata.repo_path = paths.repo_dir
        if "parallel_worker_mode" not in runtime_data and "parallel_workers" in runtime_data:
            runtime_data["parallel_worker_mode"] = "manual"
        runtime_data["parallel_worker_mode"] = normalize_parallel_worker_mode(runtime_data.get("parallel_worker_mode", "auto"))
        if "planning_effort" not in runtime_data:
            runtime_data["planning_effort"] = runtime_data.get("effort", "")
        runtime = RuntimeOptions.from_dict(runtime_data)
        counters_data = loop_state_data.get("counters", {})
        loop_state = LoopState(
            repo_id=loop_state_data["repo_id"],
            repo_slug=loop_state_data["repo_slug"],
            block_index=loop_state_data.get("block_index", 0),
            last_block_completed_at=loop_state_data.get("last_block_completed_at"),
            current_task=loop_state_data.get("current_task"),
            last_candidates=loop_state_data.get("last_candidates", []),
            last_commit_hash=loop_state_data.get("last_commit_hash"),
            current_safe_revision=loop_state_data.get("current_safe_revision"),
            plan_locked=loop_state_data.get("plan_locked", loop_state_data.get("long_term_plan_locked", True)),
            stop_reason=loop_state_data.get("stop_reason"),
            stop_requested=loop_state_data.get("stop_requested", False),
            current_checkpoint_id=loop_state_data.get("current_checkpoint_id"),
            pending_checkpoint_approval=loop_state_data.get("pending_checkpoint_approval", False),
            counters=replace(LoopCounters(), **counters_data),
        )
        return ProjectContext(metadata=metadata, runtime=runtime, paths=paths, loop_state=loop_state)

    def find_project(self, repo_url: str, branch: str) -> ProjectContext | None:
        self.ensure_workspace()
        repo_id, _ = stable_repo_identity(repo_url, branch)
        registry = self._read_registry()
        if repo_id not in registry["projects"]:
            return None
        return self.load_project_by_id(repo_id)

    def list_projects(self) -> list[ProjectContext]:
        self.ensure_workspace()
        registry = self._read_registry()
        projects: list[ProjectContext] = []
        for item in registry["projects"].values():
            try:
                projects.append(self.load_project_from_root(Path(str(item.get("project_root", "")).strip())))
            except FileNotFoundError:
                continue
        return sorted(projects, key=lambda ctx: ctx.metadata.created_at)

    def list_history_projects(self) -> list[ProjectContext]:
        self.ensure_workspace()
        registry = self._read_registry()
        history_projects: list[ProjectContext] = []
        for archive_id, item in registry["history"].items():
            try:
                context = self.load_project_from_root(Path(str(item.get("project_root", "")).strip()))
            except FileNotFoundError:
                continue
            context.metadata.archived = True
            context.metadata.archive_id = archive_id
            context.metadata.archived_at = str(item.get("archived_at", "")).strip() or context.metadata.archived_at
            context.metadata.source_repo_id = str(item.get("source_repo_id", "")).strip() or context.metadata.source_repo_id
            history_projects.append(context)
        return sorted(
            history_projects,
            key=lambda ctx: ctx.metadata.archived_at or ctx.metadata.created_at,
            reverse=True,
        )

    def find_project_by_repo_path(self, repo_path: Path) -> ProjectContext | None:
        resolved_target = repo_path.resolve()
        for project in self.list_projects():
            if project.metadata.repo_path.resolve() == resolved_target:
                return project
        return None

    def _archive_slug(self, slug: str, archived_at: str, repo_id: str) -> str:
        compact_timestamp = (
            archived_at.replace("-", "")
            .replace(":", "")
            .replace("+00:00", "Z")
            .replace("T", "T")
        )
        slug_prefix = slug.strip("-")[:20].strip("-") or "project"
        return f"{slug_prefix}-hist-{repo_id[:8]}-{compact_timestamp}-{uuid4().hex[:4]}"

    def archive_project(self, repo_id: str) -> ProjectContext:
        self.ensure_workspace()
        registry = self._read_registry()
        item = registry["projects"].pop(repo_id, None)
        if not item:
            raise KeyError(f"Unknown repository id: {repo_id}")

        source_root = Path(str(item.get("project_root", "")).strip()).resolve()
        if not source_root.exists():
            self._write_registry(registry)
            raise FileNotFoundError(f"Managed project root does not exist: {source_root}")

        context = self.load_project_from_root(source_root)
        archived_at = now_utc_iso()
        archive_id = f"hist-{uuid4().hex}"
        archive_slug = self._archive_slug(context.metadata.slug, archived_at, context.metadata.repo_id)
        archive_root = (self.history_root / archive_slug).resolve()

        if self._managed_root_is_within(source_root, self.projects_root):
            ensure_dir(self.history_root)
            shutil.move(str(source_root), str(archive_root))
        else:
            self._write_registry(registry)
            raise RuntimeError(f"Refusing to archive unexpected project root: {source_root}")

        archived_context = self._rebind_context_root(context, archive_root)
        archived_context.metadata.archived = True
        archived_context.metadata.archive_id = archive_id
        archived_context.metadata.archived_at = archived_at
        archived_context.metadata.source_repo_id = context.metadata.repo_id
        self._write_project_files(archived_context)
        registry["history"][archive_id] = self._history_registry_item(archived_context)
        self._write_registry(registry)
        return archived_context

    def delete_project(self, repo_id: str) -> ProjectContext:
        self.ensure_workspace()
        registry = self._read_registry()
        item = registry["projects"].pop(repo_id, None)
        if not item:
            raise KeyError(f"Unknown repository id: {repo_id}")

        source_root = Path(str(item.get("project_root", "")).strip()).resolve()
        if not source_root.exists():
            self._write_registry(registry)
            raise FileNotFoundError(f"Managed project root does not exist: {source_root}")

        context = self.load_project_from_root(source_root)
        self._remove_managed_project_root(source_root, self.projects_root)
        self._write_registry(registry)
        return context

    def archive_all_projects(self) -> list[ProjectContext]:
        self.ensure_workspace()
        archived: list[ProjectContext] = []
        for repo_id in list(self._read_registry().get("projects", {}).keys()):
            archived.append(self.archive_project(repo_id))
        return archived

    def delete_all_projects(self) -> list[ProjectContext]:
        self.ensure_workspace()
        deleted: list[ProjectContext] = []
        for repo_id in list(self._read_registry().get("projects", {}).keys()):
            deleted.append(self.delete_project(repo_id))
        return deleted

    def delete_history_entry(self, archive_id: str) -> ProjectContext:
        self.ensure_workspace()
        registry = self._read_registry()
        item = registry["history"].pop(archive_id, None)
        if not item:
            raise KeyError(f"Unknown archive id: {archive_id}")

        archive_root = Path(str(item.get("project_root", "")).strip()).resolve()
        if not archive_root.exists():
            self._write_registry(registry)
            raise FileNotFoundError(f"Archived project root does not exist: {archive_root}")

        context = self.load_project_from_root(archive_root)
        context.metadata.archived = True
        context.metadata.archive_id = archive_id
        context.metadata.archived_at = str(item.get("archived_at", "")).strip() or context.metadata.archived_at
        context.metadata.source_repo_id = str(item.get("source_repo_id", "")).strip() or context.metadata.source_repo_id
        self._remove_managed_project_root(archive_root, self.history_root)
        self._write_registry(registry)
        return context
