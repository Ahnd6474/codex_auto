from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .models import LoopCounters, LoopState, ProjectContext, ProjectPaths, RepoMetadata, RuntimeOptions
from .utils import ensure_dir, now_utc_iso, read_json, stable_repo_identity, write_json


class WorkspaceManager:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.projects_root = self.workspace_root / "projects"

    @property
    def registry_file(self) -> Path:
        return self.workspace_root / "registry.json"

    def ensure_workspace(self) -> None:
        ensure_dir(self.projects_root)
        if not self.registry_file.exists():
            write_json(self.registry_file, {"projects": {}})

    def build_paths(self, slug: str) -> ProjectPaths:
        project_root = self.projects_root / slug
        docs_dir = project_root / "docs"
        memory_dir = project_root / "memory"
        logs_dir = project_root / "logs"
        reports_dir = project_root / "reports"
        state_dir = project_root / "state"
        return ProjectPaths(
            workspace_root=self.workspace_root,
            projects_root=self.projects_root,
            project_root=project_root,
            repo_dir=project_root / "repo",
            docs_dir=docs_dir,
            memory_dir=memory_dir,
            logs_dir=logs_dir,
            reports_dir=reports_dir,
            state_dir=state_dir,
            metadata_file=project_root / "metadata.json",
            project_config_file=project_root / "project_config.json",
            loop_state_file=state_dir / "LOOP_STATE.json",
            long_term_plan_file=docs_dir / "LONG_TERM_PLAN.md",
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
        ]:
            ensure_dir(directory)

        registry = read_json(self.registry_file, default={"projects": {}})
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
        )
        loop_state = LoopState(repo_id=repo_id, repo_slug=slug)
        registry["projects"][repo_id] = {
            "repo_id": repo_id,
            "slug": slug,
            "repo_url": repo_url,
            "branch": branch,
            "project_root": str(paths.project_root),
        }
        write_json(self.registry_file, registry)
        self.save_project(ProjectContext(metadata=metadata, runtime=runtime, paths=paths, loop_state=loop_state))
        return self.load_project_by_id(repo_id)

    def save_project(self, context: ProjectContext) -> None:
        write_json(context.paths.metadata_file, context.metadata.to_dict())
        write_json(context.paths.project_config_file, context.runtime.to_dict())
        write_json(context.paths.loop_state_file, context.loop_state.to_dict())

    def load_project_by_id(self, repo_id: str) -> ProjectContext:
        registry = read_json(self.registry_file, default={"projects": {}})
        item = registry["projects"].get(repo_id)
        if not item:
            raise KeyError(f"Unknown repository id: {repo_id}")
        return self.load_project_by_slug(item["slug"])

    def load_project_by_slug(self, slug: str) -> ProjectContext:
        paths = self.build_paths(slug)
        metadata_data = read_json(paths.metadata_file)
        runtime_data = read_json(paths.project_config_file)
        loop_state_data = read_json(paths.loop_state_file)
        if not metadata_data or not runtime_data or not loop_state_data:
            raise FileNotFoundError(f"Project data is incomplete for slug {slug}")

        metadata = RepoMetadata(
            repo_id=metadata_data["repo_id"],
            slug=metadata_data["slug"],
            repo_url=metadata_data["repo_url"],
            branch=metadata_data["branch"],
            project_root=Path(metadata_data["project_root"]),
            repo_path=Path(metadata_data["repo_path"]),
            created_at=metadata_data["created_at"],
            last_run_at=metadata_data.get("last_run_at"),
            current_status=metadata_data.get("current_status", "initialized"),
            current_safe_revision=metadata_data.get("current_safe_revision"),
        )
        runtime = RuntimeOptions(**runtime_data)
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
            long_term_plan_locked=loop_state_data.get("long_term_plan_locked", True),
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
        registry = read_json(self.registry_file, default={"projects": {}})
        if repo_id not in registry["projects"]:
            return None
        return self.load_project_by_id(repo_id)

    def list_projects(self) -> list[ProjectContext]:
        self.ensure_workspace()
        registry = read_json(self.registry_file, default={"projects": {}})
        projects: list[ProjectContext] = []
        for item in registry["projects"].values():
            try:
                projects.append(self.load_project_by_slug(item["slug"]))
            except FileNotFoundError:
                continue
        return sorted(projects, key=lambda ctx: ctx.metadata.created_at)
