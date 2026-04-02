from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import shutil
from uuid import uuid4

from .bridge_events import emit_bridge_event
from .models import LoopCounters, LoopState, ProjectContext, ProjectPaths, RepoMetadata, RuntimeOptions
from .parallel_resources import normalize_parallel_worker_mode
from .runtime_config import runtime_from_payload
from .utils import ensure_dir, now_utc_iso, read_json, remove_tree, stable_repo_identity, write_json, write_json_if_changed

LOCAL_PROJECT_LOG_DIRNAME = "jakal-flow-logs"


class WorkspaceManager:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.projects_root = self.workspace_root / "projects"
        self.history_root = self.workspace_root / "history"
        self._registry_cache_token: tuple[int, int, int] | None = None
        self._registry_cache_value: dict[str, dict[str, dict[str, str]]] | None = None
        self._project_context_cache: dict[str, tuple[tuple[tuple[int, int, int], ...], ProjectContext]] = {}

    @property
    def registry_file(self) -> Path:
        return self.workspace_root / "registry.json"

    @staticmethod
    def _path_cache_token(path: Path) -> tuple[int, int, int]:
        try:
            stat_result = path.stat()
        except OSError:
            return (0, 0, 0)
        return (1, int(stat_result.st_mtime_ns), int(stat_result.st_size))

    @staticmethod
    def _project_cache_key(project_root: Path) -> str:
        return str(project_root.resolve())

    def _project_context_signature(self, paths: ProjectPaths) -> tuple[tuple[int, int, int], ...]:
        return (
            self._path_cache_token(paths.metadata_file),
            self._path_cache_token(paths.project_config_file),
            self._path_cache_token(paths.loop_state_file),
        )

    def _project_root_has_required_files(self, project_root: Path) -> bool:
        paths = self.build_paths_from_root(project_root)
        metadata_data = read_json(paths.metadata_file, default=None)
        runtime_data = read_json(paths.project_config_file, default=None)
        loop_state_data = read_json(paths.loop_state_file, default=None)
        return bool(metadata_data and runtime_data and loop_state_data)

    @staticmethod
    def _normalized_path(value: str | Path | None) -> Path | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return Path(text).expanduser().resolve()
        except OSError:
            return Path(text)

    def _resolve_registry_item_project_root(self, item: dict[str, str], base_dir: Path) -> Path | None:
        project_root_text = str(item.get("project_root", "")).strip()
        slug = str(item.get("slug", "")).strip()
        repo_id = str(item.get("repo_id", "")).strip() or str(item.get("source_repo_id", "")).strip()
        repo_path_text = str(item.get("repo_path", "")).strip()
        repo_path = self._normalized_path(repo_path_text)
        best_match: Path | None = None
        best_score = -1

        def consider(candidate: Path) -> None:
            nonlocal best_match, best_score
            if not candidate.exists() or not self._project_root_has_required_files(candidate):
                return
            metadata_data = read_json(self.build_paths_from_root(candidate).metadata_file, default=None)
            if not isinstance(metadata_data, dict):
                return
            child_repo_id = str(metadata_data.get("repo_id", "")).strip()
            child_slug = str(metadata_data.get("slug", "")).strip()
            child_repo_path = self._normalized_path(str(metadata_data.get("repo_path", "")).strip())

            score = 0
            if repo_path and child_repo_path and child_repo_path == repo_path:
                score = 3
            elif repo_id and child_repo_id == repo_id:
                score = 2
            elif slug and child_slug == slug:
                score = 1

            if score > best_score:
                best_match = candidate.resolve()
                best_score = score

        for candidate_text in (project_root_text, str(base_dir / slug).strip() if slug else ""):
            if candidate_text:
                consider(Path(candidate_text))

        if base_dir.exists():
            for child in base_dir.iterdir():
                if child.is_dir():
                    consider(child)

        if best_score > 0 and best_match is not None:
            return best_match
        if best_match is not None:
            return best_match
        return None

    def _sync_registry_project_root(self, repo_id: str, context: ProjectContext) -> None:
        registry = self._read_registry()
        item = registry["projects"].get(repo_id)
        normalized_item = self._active_registry_item(context)
        if item != normalized_item:
            registry["projects"][repo_id] = normalized_item
            self._write_registry(registry)

    def _sync_registry_history_root(self, archive_id: str, context: ProjectContext) -> None:
        registry = self._read_registry()
        item = registry["history"].get(archive_id)
        normalized_item = self._history_registry_item(context)
        if item != normalized_item:
            registry["history"][archive_id] = normalized_item
            self._write_registry(registry)

    def _cache_project_context(self, context: ProjectContext) -> None:
        cache_key = self._project_cache_key(context.paths.project_root)
        self._project_context_cache[cache_key] = (
            self._project_context_signature(context.paths),
            self._copy_project_context(context),
        )

    def _copy_project_context(self, context: ProjectContext) -> ProjectContext:
        copied_metadata = replace(context.metadata)
        copied_runtime = replace(context.runtime)
        copied_paths = replace(context.paths)
        copied_loop_state = replace(
            context.loop_state,
            last_candidates=deepcopy(context.loop_state.last_candidates),
            counters=replace(context.loop_state.counters),
        )
        return ProjectContext(
            metadata=copied_metadata,
            runtime=copied_runtime,
            paths=copied_paths,
            loop_state=copied_loop_state,
        )

    def _invalidate_project_context_cache(self, project_root: Path | None = None) -> None:
        if project_root is None:
            self._project_context_cache.clear()
            return
        self._project_context_cache.pop(self._project_cache_key(project_root), None)

    def _empty_registry(self) -> dict[str, dict[str, dict[str, str]]]:
        return {"projects": {}, "history": {}}

    def _read_registry(self) -> dict[str, dict[str, dict[str, str]]]:
        cache_token = self._path_cache_token(self.registry_file)
        if self._registry_cache_token == cache_token and self._registry_cache_value is not None:
            return deepcopy(self._registry_cache_value)
        raw = read_json(self.registry_file, default=self._empty_registry())
        if not isinstance(raw, dict):
            normalized = self._empty_registry()
            self._registry_cache_token = cache_token
            self._registry_cache_value = deepcopy(normalized)
            return normalized
        projects = raw.get("projects", {})
        history = raw.get("history", {})
        normalized = {
            "projects": projects if isinstance(projects, dict) else {},
            "history": history if isinstance(history, dict) else {},
        }
        self._registry_cache_token = cache_token
        self._registry_cache_value = deepcopy(normalized)
        return normalized

    def _write_registry(self, registry: dict[str, dict[str, dict[str, str]]]) -> None:
        normalized = {
            "projects": registry.get("projects", {}),
            "history": registry.get("history", {}),
        }
        write_json_if_changed(self.registry_file, normalized)
        self._registry_cache_token = self._path_cache_token(self.registry_file)
        self._registry_cache_value = deepcopy(normalized)

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

    @staticmethod
    def repo_logs_dir(repo_dir: Path) -> Path:
        return repo_dir.resolve() / LOCAL_PROJECT_LOG_DIRNAME

    def _apply_local_repo_log_paths(self, paths: ProjectPaths, repo_dir: Path) -> ProjectPaths:
        repo_logs_dir = self.repo_logs_dir(repo_dir)
        paths.logs_dir = repo_logs_dir
        paths.pass_log_file = repo_logs_dir / "passes.jsonl"
        paths.block_log_file = repo_logs_dir / "blocks.jsonl"
        paths.ui_event_log_file = repo_logs_dir / "ui_events.jsonl"
        return paths

    def _migration_conflict_path(self, target_path: Path) -> Path:
        candidate = target_path.with_name(f"{target_path.stem}.workspace-legacy{target_path.suffix}")
        index = 1
        while candidate.exists():
            candidate = target_path.with_name(f"{target_path.stem}.workspace-legacy-{index}{target_path.suffix}")
            index += 1
        return candidate

    def _prepend_jsonl_file(self, source_path: Path, target_path: Path) -> None:
        source_bytes = source_path.read_bytes()
        target_bytes = target_path.read_bytes()
        if not source_bytes:
            source_path.unlink(missing_ok=True)
            return
        if not target_bytes:
            target_path.write_bytes(source_bytes)
            source_path.unlink(missing_ok=True)
            return
        combined = bytearray(source_bytes)
        if not source_bytes.endswith(b"\n"):
            combined.extend(b"\n")
        combined.extend(target_bytes)
        target_path.write_bytes(bytes(combined))
        source_path.unlink(missing_ok=True)

    def _merge_logs_file(self, source_path: Path, target_path: Path) -> None:
        ensure_dir(target_path.parent)
        if not target_path.exists():
            shutil.move(str(source_path), str(target_path))
            return
        if target_path.is_dir():
            shutil.move(str(source_path), str(self._migration_conflict_path(target_path.parent / source_path.name)))
            return
        if source_path.read_bytes() == target_path.read_bytes():
            source_path.unlink(missing_ok=True)
            return
        if source_path.suffix == ".jsonl" and target_path.suffix == ".jsonl":
            self._prepend_jsonl_file(source_path, target_path)
            return
        shutil.move(str(source_path), str(self._migration_conflict_path(target_path)))

    def _merge_logs_directory(self, source_dir: Path, target_dir: Path) -> None:
        if target_dir.exists() and not target_dir.is_dir():
            shutil.move(str(target_dir), str(self._migration_conflict_path(target_dir)))
        ensure_dir(target_dir)
        for child in list(source_dir.iterdir()):
            destination = target_dir / child.name
            if child.is_dir():
                self._merge_logs_directory(child, destination)
            else:
                self._merge_logs_file(child, destination)
        remove_tree(source_dir, ignore_errors=True)

    def migrate_logs_dir(self, source_logs_dir: Path, target_logs_dir: Path) -> None:
        if not source_logs_dir.exists():
            return
        resolved_source = source_logs_dir.resolve()
        resolved_target = target_logs_dir.resolve()
        if resolved_source == resolved_target:
            return
        self._merge_logs_directory(source_logs_dir, target_logs_dir)
        if source_logs_dir.exists():
            try:
                next(source_logs_dir.iterdir())
            except StopIteration:
                source_logs_dir.rmdir()
            except OSError:
                pass

    def _migrate_local_project_logs(self, project_root: Path, repo_dir: Path) -> None:
        self.migrate_logs_dir(project_root.resolve() / "logs", self.repo_logs_dir(repo_dir))

    def build_paths_from_root(self, project_root: Path) -> ProjectPaths:
        resolved_root = project_root.resolve()
        docs_dir = resolved_root / "docs"
        memory_dir = resolved_root / "memory"
        logs_dir = resolved_root / "logs"
        reports_dir = resolved_root / "reports"
        state_dir = resolved_root / "state"
        lineage_manifests_dir = state_dir / "lineage_manifests"
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
            planning_metrics_file=logs_dir / "planning_metrics.jsonl",
            checkpoint_state_file=state_dir / "CHECKPOINTS.json",
            execution_plan_file=state_dir / "EXECUTION_PLAN.json",
            planning_inputs_cache_file=state_dir / "PLANNING_INPUTS_CACHE.json",
            planning_prompt_cache_file=state_dir / "PLANNING_PROMPT_CACHE.json",
            block_plan_cache_file=state_dir / "BLOCK_PLAN_CACHE.json",
            lineage_state_file=state_dir / "LINEAGES.json",
            spine_file=state_dir / "SPINE.json",
            common_requirements_file=state_dir / "COMMON_REQUIREMENTS.json",
            contract_wave_audit_file=state_dir / "CONTRACT_WAVE_AUDIT.jsonl",
            ml_mode_state_file=state_dir / "ML_MODE_STATE.json",
            ml_step_report_file=state_dir / "ML_STEP_REPORT.json",
            ml_experiment_reports_dir=state_dir / "ml_experiments",
            lineage_manifests_dir=lineage_manifests_dir,
            ui_control_file=state_dir / "UI_RUN_CONTROL.json",
            ui_event_log_file=logs_dir / "ui_events.jsonl",
            execution_flow_svg_file=docs_dir / "EXECUTION_FLOW.svg",
            closeout_report_file=docs_dir / "CLOSEOUT_REPORT.md",
            closeout_report_docx_file=reports_dir / "CLOSEOUT_REPORT.docx",
            closeout_report_pptx_file=reports_dir / "CLOSEOUT_REPORT.pptx",
            ml_experiment_report_file=docs_dir / "ML_EXPERIMENT_REPORT.md",
            ml_experiment_results_svg_file=docs_dir / "ML_EXPERIMENT_RESULTS.svg",
            shared_contracts_file=docs_dir / "SHARED_CONTRACTS.md",
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
            paths.lineage_manifests_dir,
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
            paths.lineage_manifests_dir,
        ]:
            ensure_dir(directory)
        ensure_dir(resolved_dir)
        self._migrate_local_project_logs(paths.project_root, resolved_dir)

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
        write_json_if_changed(context.paths.metadata_file, context.metadata.to_dict())
        write_json_if_changed(context.paths.project_config_file, context.runtime.to_dict())
        write_json_if_changed(context.paths.loop_state_file, context.loop_state.to_dict())
        self._cache_project_context(context)

    def _managed_root_is_within(self, project_root: Path, expected_parent: Path) -> bool:
        resolved_root = project_root.resolve()
        resolved_parent = expected_parent.resolve()
        return resolved_root != resolved_parent and resolved_parent in resolved_root.parents

    def _rebind_context_root(self, context: ProjectContext, project_root: Path) -> ProjectContext:
        previous_root = context.paths.project_root
        resolved_root = project_root.resolve()
        context.metadata.project_root = resolved_root
        context.paths = self.build_paths_from_root(resolved_root)
        if context.metadata.repo_kind == "local":
            context.paths.repo_dir = context.metadata.repo_path
            context.paths = self._apply_local_repo_log_paths(context.paths, context.metadata.repo_path)
            self._migrate_local_project_logs(resolved_root, context.metadata.repo_path)
        else:
            context.metadata.repo_path = context.paths.repo_dir
        self._invalidate_project_context_cache(previous_root)
        self._invalidate_project_context_cache(resolved_root)
        return context

    def _remove_managed_project_root(self, project_root: Path, expected_parent: Path) -> None:
        resolved_root = project_root.resolve()
        if not self._managed_root_is_within(resolved_root, expected_parent):
            raise RuntimeError(f"Refusing to delete unexpected project root: {resolved_root}")
        self._invalidate_project_context_cache(resolved_root)
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
                        "current_checkpoint_id": str(context.loop_state.current_checkpoint_id or "").strip(),
                        "current_checkpoint_lineage_id": str(context.loop_state.current_checkpoint_lineage_id or "").strip(),
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

    def _cached_registered_context(self, registry_root_text: str) -> ProjectContext | None:
        registry_root = self._normalized_path(registry_root_text)
        if registry_root is None:
            return None
        cache_key = self._project_cache_key(registry_root)
        cached = self._project_context_cache.get(cache_key)
        if cached is None:
            return None
        if cached[0] != self._project_context_signature(self.build_paths_from_root(registry_root)):
            return None
        return self._copy_project_context(cached[1])

    def _apply_history_registry_metadata(
        self,
        context: ProjectContext,
        *,
        archive_id: str,
        item: dict[str, str],
    ) -> ProjectContext:
        context.metadata.archived = True
        context.metadata.archive_id = archive_id
        context.metadata.archived_at = str(item.get("archived_at", "")).strip() or context.metadata.archived_at
        context.metadata.source_repo_id = str(item.get("source_repo_id", "")).strip() or context.metadata.source_repo_id
        return context

    def _load_registered_context(
        self,
        entry_id: str,
        *,
        registry_section: str,
        base_dir: Path,
        missing_error_label: str,
        transform_context: Callable[[ProjectContext, dict[str, str]], ProjectContext] | None = None,
        sync_registry_root: Callable[[str, ProjectContext], None] | None = None,
    ) -> ProjectContext:
        registry = self._read_registry()
        item = registry[registry_section].get(entry_id)
        if not item:
            raise KeyError(f"Unknown {missing_error_label}: {entry_id}")
        registry_root_text = str(item.get("project_root", "")).strip()
        cached = self._cached_registered_context(registry_root_text)
        if cached is not None:
            return transform_context(cached, item) if transform_context is not None else cached
        resolved_root = self._resolve_registry_item_project_root(item, base_dir)
        if resolved_root is None:
            resolved_root = Path(registry_root_text)
        context = self.load_project_from_root(resolved_root)
        if transform_context is not None:
            context = transform_context(context, item)
        if sync_registry_root is not None:
            sync_registry_root(entry_id, context)
        return context

    def load_project_by_id(self, repo_id: str) -> ProjectContext:
        return self._load_registered_context(
            repo_id,
            registry_section="projects",
            base_dir=self.projects_root,
            missing_error_label="repository id",
            sync_registry_root=self._sync_registry_project_root,
        )

    def load_history_by_id(self, archive_id: str) -> ProjectContext:
        return self._load_registered_context(
            archive_id,
            registry_section="history",
            base_dir=self.history_root,
            missing_error_label="archive id",
            transform_context=lambda context, item: self._apply_history_registry_metadata(
                context,
                archive_id=archive_id,
                item=item,
            ),
            sync_registry_root=self._sync_registry_history_root,
        )

    def load_project_by_slug(self, slug: str) -> ProjectContext:
        return self.load_project_from_root(self.projects_root / slug)

    def load_project_from_root(self, project_root: Path) -> ProjectContext:
        paths = self.build_paths_from_root(project_root)
        metadata_data = None
        legacy_logs_dir = paths.project_root / "logs"
        if legacy_logs_dir.exists():
            metadata_data = read_json(paths.metadata_file)
            if isinstance(metadata_data, dict) and str(metadata_data.get("repo_kind", "remote")).strip() == "local":
                repo_path_hint = Path(str(metadata_data.get("repo_path", "")).strip())
                paths.repo_dir = repo_path_hint
                paths = self._apply_local_repo_log_paths(paths, repo_path_hint)
                self._migrate_local_project_logs(paths.project_root, repo_path_hint)
        cache_key = self._project_cache_key(paths.project_root)
        signature = self._project_context_signature(paths)
        cached = self._project_context_cache.get(cache_key)
        if cached is not None and cached[0] == signature:
            return self._copy_project_context(cached[1])
        if metadata_data is None:
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
            self._migrate_local_project_logs(paths.project_root, metadata.repo_path)
        else:
            metadata.repo_path = paths.repo_dir
        runtime = runtime_from_payload(runtime_data)
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
            current_checkpoint_lineage_id=loop_state_data.get("current_checkpoint_lineage_id"),
            pending_checkpoint_approval=loop_state_data.get("pending_checkpoint_approval", False),
            counters=replace(LoopCounters(), **counters_data),
        )
        context = ProjectContext(metadata=metadata, runtime=runtime, paths=paths, loop_state=loop_state)
        self._project_context_cache[cache_key] = (signature, self._copy_project_context(context))
        return context

    def find_project(self, repo_url: str, branch: str) -> ProjectContext | None:
        self.ensure_workspace()
        repo_id, _ = stable_repo_identity(repo_url, branch)
        registry = self._read_registry()
        if repo_id not in registry["projects"]:
            return None
        return self.load_project_by_id(repo_id)

    def _list_registered_contexts(
        self,
        registry_section: str,
        *,
        load_context: Callable[[str], ProjectContext],
    ) -> list[ProjectContext]:
        self.ensure_workspace()
        registry = self._read_registry()
        contexts: list[ProjectContext] = []
        for entry_id in registry.get(registry_section, {}).keys():
            try:
                contexts.append(load_context(entry_id))
            except (FileNotFoundError, KeyError):
                continue
        return contexts

    def list_projects(self) -> list[ProjectContext]:
        return sorted(
            self._list_registered_contexts("projects", load_context=self.load_project_by_id),
            key=lambda ctx: ctx.metadata.created_at,
        )

    def list_history_projects(self) -> list[ProjectContext]:
        history_projects = self._list_registered_contexts("history", load_context=self.load_history_by_id)
        return sorted(
            history_projects,
            key=lambda ctx: ctx.metadata.archived_at or ctx.metadata.created_at,
            reverse=True,
        )

    def find_project_by_repo_path(self, repo_path: Path) -> ProjectContext | None:
        self.ensure_workspace()
        resolved_target = repo_path.resolve()
        registry = self._read_registry()
        for repo_id, item in registry["projects"].items():
            if self._normalized_path(item.get("repo_path", "")) == resolved_target:
                try:
                    return self.load_project_by_id(repo_id)
                except (FileNotFoundError, KeyError):
                    break
        for repo_id in registry["projects"].keys():
            try:
                project = self.load_project_by_id(repo_id)
            except (FileNotFoundError, KeyError):
                continue
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
