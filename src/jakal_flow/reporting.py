from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
from xml.sax.saxutils import escape
import zipfile

from .contract_wave import load_lineage_manifest_payloads
from .failure_logs import collect_failure_artifacts
from .github_api import GitHubAPIError, GitHubClient, parse_github_repository_url
from .models import ExecutionPlanState, ProjectContext, TestRunResult
from .utils import append_jsonl, append_text, compact_text, now_utc_iso, read_json, read_jsonl_tail, read_text, write_json, write_text


class Reporter:
    _LOGX_TEXT_PREVIEW_SUFFIXES = {
        ".json",
        ".jsonl",
        ".log",
        ".md",
        ".prompt",
        ".stderr",
        ".stdout",
        ".txt",
    }
    _LOGX_LOCAL_LOG_DIRNAME = "jakal-flow-logs"
    _GENERIC_WORKER_SUMMARIES = {
        "lineage worker did not complete.",
        "lineage worker failed.",
        "lineage worker finished.",
        "parallel worker did not complete.",
        "parallel worker failed.",
        "parallel worker finished.",
    }

    def __init__(self, context: ProjectContext) -> None:
        self.context = context

    @staticmethod
    def _normalize_merge_method(value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"merge", "rebase", "squash"}:
            return normalized
        return "squash"

    def _attempt_pull_request_merge(
        self,
        client: GitHubClient,
        *,
        owner: str,
        repo: str,
        pull_request: int,
        title: str,
        merge_method: str,
    ) -> dict:
        normalized_method = self._normalize_merge_method(merge_method)
        try:
            auto_merge_result = client.enable_pull_request_auto_merge(
                owner,
                repo,
                pull_request,
                merge_method=normalized_method.upper(),
            )
            return {
                "auto_merge_requested": True,
                "auto_merge_enabled": True,
                "merged": False,
                "merge_method": normalized_method,
                "auto_merge_result": auto_merge_result,
            }
        except GitHubAPIError as auto_merge_exc:
            try:
                merge_result = client.merge_pull_request(
                    owner,
                    repo,
                    pull_request,
                    merge_method=normalized_method,
                    commit_title=title,
                )
                return {
                    "auto_merge_requested": True,
                    "auto_merge_enabled": False,
                    "merged": True,
                    "merge_method": normalized_method,
                    "auto_merge_error": str(auto_merge_exc),
                    "merge_result": merge_result,
                }
            except GitHubAPIError as merge_exc:
                return {
                    "auto_merge_requested": True,
                    "auto_merge_enabled": False,
                    "merged": False,
                    "merge_method": normalized_method,
                    "auto_merge_error": str(auto_merge_exc),
                    "merge_error": str(merge_exc),
                }

    def log_pass(self, data: dict) -> None:
        append_jsonl(self.context.paths.pass_log_file, data)

    def log_block(self, data: dict) -> None:
        append_jsonl(self.context.paths.block_log_file, data)

    def append_attempt_history(self, content: str) -> None:
        append_text(self.context.paths.attempt_history_file, content)

    def write_block_review(self, content: str) -> None:
        write_text(self.context.paths.block_review_file, content)

    def write_status_report(self) -> Path:
        passes = read_jsonl_tail(self.context.paths.pass_log_file, 20)
        blocks = read_jsonl_tail(self.context.paths.block_log_file, 20)
        verification_profile_metrics = self._verification_profile_metrics()
        report = {
            "generated_at": now_utc_iso(),
            "repository": self.context.metadata.to_dict(),
            "loop_state": self.context.loop_state.to_dict(),
            "recent_passes": passes,
            "recent_blocks": blocks,
            "verification_profiles": verification_profile_metrics,
            "planning_metrics": read_jsonl_tail(self.context.paths.planning_metrics_file, 40),
            "spine": read_json(self.context.paths.spine_file, default={}),
            "common_requirements": read_json(self.context.paths.common_requirements_file, default={}),
            "lineage_manifests": load_lineage_manifest_payloads(self.context.paths),
        }
        path = self.context.paths.reports_dir / "latest_report.json"
        write_json(path, report)
        return path

    @classmethod
    def _normalized_summary_text(cls, value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    @classmethod
    def _is_generic_worker_summary(cls, value: str) -> bool:
        return cls._normalized_summary_text(value) in cls._GENERIC_WORKER_SUMMARIES

    @classmethod
    def clean_logged_failure_detail(cls, detail: str) -> str:
        kept_lines: list[str] = []
        for raw_line in str(detail or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.lower()
            if lowered in {
                "yolo mode is enabled. all tool calls will be automatically approved.",
                "loaded cached credentials.",
            }:
                continue
            kept_lines.append(line)
        return compact_text(" ".join(kept_lines), max_chars=280) if kept_lines else ""

    @classmethod
    def logged_pass_failure_detail(cls, pass_entry: dict[str, object]) -> str:
        if not isinstance(pass_entry, dict):
            return ""
        test_results = pass_entry.get("test_results")
        if isinstance(test_results, dict):
            for key in ("failure_reason", "summary"):
                detail = cls.clean_logged_failure_detail(str(test_results.get(key) or ""))
                if detail:
                    return detail
        diagnostics = pass_entry.get("codex_diagnostics")
        attempts = diagnostics.get("attempts", []) if isinstance(diagnostics, dict) else []
        for attempt in reversed(attempts if isinstance(attempts, list) else []):
            if not isinstance(attempt, dict):
                continue
            for key in ("stderr_excerpt", "last_message_excerpt", "stdout_excerpt"):
                detail = cls.clean_logged_failure_detail(str(attempt.get(key) or ""))
                if detail:
                    return detail
        failure_type = compact_text(str(pass_entry.get("failure_type") or "").strip(), max_chars=120)
        failure_reason_code = compact_text(str(pass_entry.get("failure_reason_code") or "").strip(), max_chars=120)
        if failure_type or failure_reason_code:
            return " / ".join(part for part in [failure_type, failure_reason_code] if part)
        return ""

    @classmethod
    def summarize_logged_result(
        cls,
        *,
        block_entry: dict[str, object] | None,
        pass_entry: dict[str, object] | None,
        completed_summary: str,
        failed_summary: str,
    ) -> str:
        block_payload = block_entry if isinstance(block_entry, dict) else {}
        pass_payload = pass_entry if isinstance(pass_entry, dict) else {}
        status = str(block_payload.get("status") or pass_payload.get("status") or "").strip().lower()
        block_summary = compact_text(str(block_payload.get("test_summary") or "").strip(), max_chars=280)
        if block_summary and not (status != "completed" and cls._is_generic_worker_summary(block_summary)):
            return block_summary
        if status == "completed":
            return completed_summary
        failure_detail = cls.logged_pass_failure_detail(pass_payload)
        if failure_detail:
            return f"{failed_summary} Cause: {failure_detail}"
        rollback_status = str(block_payload.get("rollback_status") or pass_payload.get("rollback_status") or "").strip()
        if rollback_status and rollback_status != "not_needed":
            return f"{failed_summary} It was {rollback_status.replace('_', ' ')}."
        if block_summary:
            return block_summary
        return failed_summary

    @staticmethod
    def _logx_kind(path: Path) -> str:
        name = path.name.lower()
        if name.endswith(".stderr.log"):
            return "stderr_log"
        if name.endswith(".stdout.log"):
            return "stdout_log"
        if name.endswith(".events.jsonl"):
            return "event_log"
        if name.endswith(".jsonl"):
            return "jsonl"
        if name.endswith(".json"):
            return "json"
        if name.endswith(".md"):
            return "markdown"
        if name.endswith(".txt"):
            return "text"
        return "file"

    @classmethod
    def _logx_entry(cls, path: Path, *, max_preview_chars: int) -> dict[str, object]:
        try:
            stat_result = path.stat()
            size_bytes = int(stat_result.st_size)
            mtime_ns = int(stat_result.st_mtime_ns)
        except OSError:
            return {
                "path": str(path),
                "name": path.name,
                "kind": cls._logx_kind(path),
                "size_bytes": 0,
                "mtime_ns": 0,
                "checksum": "",
                "preview": "",
            }

        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(2 ** 20)
                    if not chunk:
                        break
                    digest.update(chunk)
            checksum = digest.hexdigest()
        except OSError:
            checksum = ""

        suffixes = {suffix.lower() for suffix in path.suffixes}
        preview = ""
        if suffixes.intersection(cls._LOGX_TEXT_PREVIEW_SUFFIXES):
            try:
                preview = compact_text(
                    path.read_text(encoding="utf-8", errors="replace"),
                    max_chars=max_preview_chars,
                )
            except OSError:
                preview = ""

        return {
            "path": str(path),
            "name": path.name,
            "kind": cls._logx_kind(path),
            "size_bytes": size_bytes,
            "mtime_ns": mtime_ns,
            "checksum": checksum,
            "preview": preview,
        }

    @classmethod
    def _logx_log_dir(cls, project_root: Path) -> Path:
        resolved_root = project_root.resolve()
        candidates = [
            resolved_root / "logs",
            resolved_root / cls._LOGX_LOCAL_LOG_DIRNAME,
            resolved_root / f".{cls._LOGX_LOCAL_LOG_DIRNAME}",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return resolved_root / "logs"

    def _collect_logx_candidates(self, *, max_artifacts: int, source_repo_dir: Path | None = None) -> list[Path]:
        root = self.context.paths.project_root if source_repo_dir is None else source_repo_dir
        root = root.resolve()
        logs_dir = self.context.paths.logs_dir if source_repo_dir is None else self._logx_log_dir(root)
        candidates: list[Path] = []
        if logs_dir.exists():
            candidates.extend(
                sorted(path for path in logs_dir.rglob("*") if path.is_file())
            )
        for path in [
            root / "metadata.json",
            root / "project_config.json",
            root / "state" / "LOOP_STATE.json",
            root / "state" / "EXECUTION_PLAN.json",
            root / "state" / "PLANNING_INPUTS_CACHE.json",
            root / "state" / "PLANNING_PROMPT_CACHE.json",
            root / "state" / "BLOCK_PLAN_CACHE.json",
            root / "state" / "CHECKPOINTS.json",
            root / "state" / "SPINE.json",
            root / "state" / "COMMON_REQUIREMENTS.json",
            root / "state" / "ML_MODE_STATE.json",
            root / "state" / "LINEAGES.json",
            root / "docs" / "PLAN.md",
            root / "docs" / "BLOCK_REVIEW.md",
            root / "docs" / "CLOSEOUT_REPORT.md",
            root / "docs" / "ML_EXPERIMENT_REPORT.md",
            root / "memory" / "success_patterns.jsonl",
            root / "memory" / "failure_patterns.jsonl",
            root / "memory" / "task_summaries.jsonl",
            root / "reports" / "latest_report.json",
        ]:
            if path.exists():
                candidates.append(path)
        if max_artifacts > 0:
            return sorted(set(candidates), key=lambda item: (item.parent.as_posix(), item.name))[: max_artifacts]
        return sorted(set(candidates), key=lambda item: (item.parent.as_posix(), item.name))

    def _logx_index(
        self,
        path: Path,
        *,
        artifacts: list[dict[str, object]],
        source_repo_dir: Path | None = None,
    ) -> tuple[dict[str, object], int]:
        existing_payload = read_json(path, default={})
        previous_entries = existing_payload.get("entries", [])
        existing_by_path: dict[str, dict[str, object]] = {}
        if isinstance(previous_entries, list):
            for entry in previous_entries:
                if not isinstance(entry, dict):
                    continue
                entry_path = str(entry.get("path", "")).strip()
                if entry_path:
                    existing_by_path[entry_path] = entry

        merged: dict[str, dict[str, object]] = {}
        updated_count = 0
        for entry in artifacts:
            key = str(entry.get("path") or "").strip()
            if not key:
                continue
            previous = existing_by_path.get(key)
            if (
                not isinstance(previous, dict)
                or previous.get("checksum") != entry.get("checksum")
                or previous.get("size_bytes") != entry.get("size_bytes")
                or previous.get("mtime_ns") != entry.get("mtime_ns")
            ):
                updated_count += 1
            merged[key] = entry

        ordered_entries = [merged[key] for key in sorted(merged.keys())]
        return {
            "generated_at": now_utc_iso(),
            "repository": self.context.metadata.to_dict(),
            "loop_state": self.context.loop_state.to_dict(),
            "project_root": str(self.context.paths.project_root),
            "source_repo_dir": str(source_repo_dir) if source_repo_dir is not None else str(self.context.paths.project_root),
            "repo_url": str(self.context.metadata.repo_url),
            "repo_branch": str(self.context.metadata.branch),
            "project_logs_dir": str(self.context.paths.logs_dir),
            "entries": ordered_entries,
            "stats": {
                "candidate_count": len(artifacts),
                "tracked_count": len(ordered_entries),
                "updated_count": updated_count,
            },
        }, updated_count

    def write_logx(
        self,
        *,
        max_artifacts: int = 400,
        max_preview_chars: int = 2_400,
        source_repo_dir: Path | None = None,
    ) -> Path:
        candidates = self._collect_logx_candidates(max_artifacts=max_artifacts, source_repo_dir=source_repo_dir)
        if not candidates:
            path = self.context.paths.reports_dir / "logx.json"
            write_json(path, {"generated_at": now_utc_iso(), "entries": []})
            return path
        artifacts = [self._logx_entry(path, max_preview_chars=max_preview_chars) for path in candidates]
        path = self.context.paths.reports_dir / "logx.json"
        payload, _ = self._logx_index(path, artifacts=artifacts, source_repo_dir=source_repo_dir)
        write_json(path, payload)
        return path

    def write_closeout_word_report(self) -> Path:
        source_text = read_text(
            self.context.paths.closeout_report_file,
            default="# Closeout Report\n\nNo closeout has been run yet.\n",
        )
        paragraphs = [line.strip() for line in source_text.splitlines()]
        body = []
        for paragraph in paragraphs:
            text = escape(paragraph) if paragraph else ""
            body.append(
                "<w:p><w:r><w:t xml:space=\"preserve\">"
                f"{text}"
                "</w:t></w:r></w:p>"
            )
        if not body:
            body.append("<w:p><w:r><w:t>Closeout Report</w:t></w:r></w:p>")

        document_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
            f"<w:body>{''.join(body)}"
            "<w:sectPr><w:pgSz w:w=\"12240\" w:h=\"15840\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" "
            "w:bottom=\"1440\" w:left=\"1440\" w:header=\"720\" w:footer=\"720\" w:gutter=\"0\"/></w:sectPr>"
            "</w:body></w:document>"
        )
        content_types_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
            "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
            "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
            "<Override PartName=\"/word/document.xml\" "
            "ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
            "</Types>"
        )
        rels_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" "
            "Target=\"word/document.xml\"/>"
            "</Relationships>"
        )
        path = self.context.paths.closeout_report_docx_file
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types_xml)
            archive.writestr("_rels/.rels", rels_xml)
            archive.writestr("word/document.xml", document_xml)
        return path

    def render_history(self, limit: int = 10) -> str:
        entries = read_jsonl_tail(self.context.paths.block_log_file, limit)
        if not entries:
            return "No block history recorded."
        lines = []
        for item in entries:
            lines.append(
                f"block={item['block_index']} lineage={item.get('lineage_id') or 'n/a'} status={item['status']} task={item['selected_task']} commits={','.join(item.get('commit_hashes', [])) or 'none'}"
            )
        return "\n".join(lines)

    def save_test_result(self, block_index: int, label: str, result: TestRunResult) -> None:
        payload = result.to_dict()
        payload["block_index"] = block_index
        payload["label"] = label
        append_jsonl(self.context.paths.logs_dir / "test_runs.jsonl", payload)

    def _verification_profile_metrics(self) -> dict[str, object]:
        execution_plan_payload = read_json(self.context.paths.execution_plan_file, default=None)
        execution_plan = (
            ExecutionPlanState.from_dict(execution_plan_payload)
            if isinstance(execution_plan_payload, dict)
            else ExecutionPlanState(default_test_command=str(self.context.runtime.test_cmd or "").strip())
        )
        profile_counts: dict[str, int] = {}
        source_counts: dict[str, int] = {}
        for step in execution_plan.steps:
            profile = str(step.verification_profile or "").strip().lower() or "default"
            profile_counts[profile] = profile_counts.get(profile, 0) + 1
            metadata = step.metadata if isinstance(step.metadata, dict) else {}
            source = str(metadata.get("verification_profile_source", "")).strip().lower() or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1

        recent_test_runs = read_jsonl_tail(self.context.paths.logs_dir / "test_runs.jsonl", 200)
        command_source_counts: dict[str, int] = {}
        for entry in recent_test_runs:
            if not isinstance(entry, dict):
                continue
            source = str(entry.get("verification_command_source", "")).strip().lower()
            if not source:
                continue
            command_source_counts[source] = command_source_counts.get(source, 0) + 1

        total_steps = sum(profile_counts.values())
        fallback_default_count = int(source_counts.get("fallback_default", 0))
        return {
            "total_steps": total_steps,
            "profile_counts": profile_counts,
            "profile_source_counts": source_counts,
            "fallback_default_count": fallback_default_count,
            "fallback_default_rate": round(fallback_default_count / total_steps, 4) if total_steps else 0.0,
            "recent_command_source_counts": command_source_counts,
        }

    def write_failure_bundle(
        self,
        failure_type: str,
        summary: str,
        *,
        block_index: int | None = None,
        selected_task: str = "",
        extra: dict | None = None,
    ) -> dict:
        latest_report = read_json(self.context.paths.reports_dir / "latest_report.json", default={})
        recent_passes = read_jsonl_tail(self.context.paths.pass_log_file, 5)
        recent_blocks = read_jsonl_tail(self.context.paths.block_log_file, 5)
        recent_tests = read_jsonl_tail(self.context.paths.logs_dir / "test_runs.jsonl", 5)
        extra_payload = dict(extra) if isinstance(extra, dict) else {}
        artifact_candidates = extra_payload.get("artifact_paths", [])
        artifact_paths = artifact_candidates if isinstance(artifact_candidates, list) else []
        if artifact_paths:
            extra_payload["artifact_paths"] = [str(item).strip() for item in artifact_paths if str(item).strip()]
        artifacts = collect_failure_artifacts(
            self.context,
            block_index=block_index,
            extra_paths=[Path(str(item)) for item in artifact_paths if str(item).strip()],
        )
        generated_at = now_utc_iso()
        safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in failure_type.strip().lower())
        safe_name = (safe_name.strip("-") or "failure")[:16]
        timestamp_token = "".join(char for char in generated_at if char.isdigit())[:14] or "00000000000000"
        stem = f"{timestamp_token}_{safe_name}"
        json_path = self.context.paths.reports_dir / f"{stem}.prfail.json"
        md_path = self.context.paths.reports_dir / f"{stem}.prfail.md"
        payload = {
            "generated_at": generated_at,
            "failure_type": failure_type,
            "summary": summary.strip(),
            "selected_task": selected_task.strip(),
            "block_index": block_index,
            "repository": self.context.metadata.to_dict(),
            "loop_state": self.context.loop_state.to_dict(),
            "recent_blocks": recent_blocks,
            "recent_passes": recent_passes,
            "recent_test_runs": recent_tests,
            "latest_report": latest_report if isinstance(latest_report, dict) else {},
            "extra": extra_payload,
            "artifacts": artifacts,
            "artifact_files": [item["path"] for item in artifacts],
            "report_json_file": str(json_path),
            "report_markdown_file": str(md_path),
        }
        write_json(json_path, payload)
        write_text(md_path, self.format_pr_failure_report(payload))
        return payload

    def format_pr_failure_report(self, bundle: dict) -> str:
        repository = bundle.get("repository", {})
        extra = bundle.get("extra", {})
        lines = [
            "## jakal-flow failure report",
            "",
            f"- Generated at: {bundle.get('generated_at', '')}",
            f"- Repository: {repository.get('display_name') or repository.get('slug') or repository.get('repo_url') or 'unknown'}",
            f"- Branch: {repository.get('branch') or 'unknown'}",
            f"- Failure type: {bundle.get('failure_type') or 'unknown'}",
            f"- Block index: {bundle.get('block_index') if bundle.get('block_index') is not None else 'n/a'}",
            f"- Task: {bundle.get('selected_task') or 'n/a'}",
            "",
            "### Summary",
            "",
            compact_text(str(bundle.get("summary", "")).strip() or "No summary recorded.", max_chars=1200),
            "",
        ]
        conflict = extra.get("conflict") if isinstance(extra, dict) else None
        if isinstance(conflict, dict):
            files = conflict.get("files") or []
            lines.extend(
                [
                    "### Conflict Policy",
                    "",
                    f"- Policy: {conflict.get('policy') or 'manual'}",
                    f"- Recommended action: {conflict.get('recommended_action') or 'manual_review'}",
                    f"- Conflicted files: {', '.join(str(item) for item in files) or 'none'}",
                    f"- Procedure: {conflict.get('procedure') or 'Inspect files, resolve conflicts, rerun safely.'}",
                    "",
                ]
            )
        lines.extend(["### Recent Blocks", ""])
        for item in bundle.get("recent_blocks", []) or []:
            lines.append(
                f"- block={item.get('block_index')} lineage={item.get('lineage_id') or 'n/a'} status={item.get('status')} task={item.get('selected_task')} summary={compact_text(str(item.get('test_summary', '')), 180)}"
            )
        if not (bundle.get("recent_blocks") or []):
            lines.append("- none")
        lines.extend(["", "### Recent Passes", ""])
        for item in bundle.get("recent_passes", []) or []:
            lines.append(
                f"- block={item.get('block_index')} pass={item.get('pass_type')} code={item.get('codex_return_code')} rollback={item.get('rollback_status')}"
            )
        if not (bundle.get("recent_passes") or []):
            lines.append("- none")
        lines.extend(["", "### Failure Artifacts", ""])
        for item in bundle.get("artifacts", []) or []:
            lines.append(
                f"- {item.get('kind') or 'file'}: `{item.get('path') or ''}`"
            )
        if not (bundle.get("artifacts") or []):
            lines.append("- none")
        lines.extend(
            [
                "",
                "### Report Files",
                "",
                f"- JSON: `{bundle.get('report_json_file', '')}`",
                f"- Markdown: `{bundle.get('report_markdown_file', '')}`",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    def post_pr_failure_report(self, bundle: dict) -> dict:
        token = self.github_token()
        repo_url = self.context.metadata.origin_url or self.context.metadata.repo_url
        repository = parse_github_repository_url(repo_url or "")
        if not token:
            return {"posted": False, "reason": "missing_github_token"}
        if repository is None:
            return {"posted": False, "reason": "non_github_origin"}
        owner, repo = repository
        try:
            client = GitHubClient(token=token)
            pull_request = client.find_open_pull_request_for_branch(owner, repo, self.context.metadata.branch)
            if not pull_request:
                return {"posted": False, "reason": "no_open_pull_request", "owner": owner, "repo": repo}
            issue_number = int(pull_request.get("number", 0))
            if issue_number <= 0:
                return {"posted": False, "reason": "invalid_pull_request_number", "owner": owner, "repo": repo}
            body = self.format_pr_failure_report(bundle)
            comment = client.post_issue_comment(owner, repo, issue_number, body)
            return {
                "posted": True,
                "owner": owner,
                "repo": repo,
                "pull_request": issue_number,
                "comment_url": comment.get("html_url", ""),
            }
        except GitHubAPIError as exc:
            return {"posted": False, "reason": "github_api_error", "error": str(exc)}

    @staticmethod
    def github_token() -> str:
        return (
            os.environ.get("JAKAL_FLOW_GITHUB_TOKEN", "").strip()
            or os.environ.get("GITHUB_TOKEN", "").strip()
            or os.environ.get("GH_TOKEN", "").strip()
        )

    def ensure_pull_request(
        self,
        *,
        head_branch: str,
        base_branch: str = "",
        title: str,
        body: str = "",
        draft: bool = False,
        auto_merge: bool = False,
        merge_method: str = "squash",
    ) -> dict:
        token = self.github_token()
        repo_url = self.context.metadata.origin_url or self.context.metadata.repo_url
        repository = parse_github_repository_url(repo_url or "")
        if not token:
            return {"created": False, "reason": "missing_github_token"}
        if repository is None:
            return {"created": False, "reason": "non_github_origin"}

        head = head_branch.strip()
        if not head:
            return {"created": False, "reason": "missing_head_branch"}

        owner, repo = repository
        try:
            client = GitHubClient(token=token)
            resolved_base = base_branch.strip()
            if not resolved_base or resolved_base == head:
                repository_info = client.get_repository(owner, repo)
                resolved_base = repository_info.default_branch.strip() or resolved_base
            if not resolved_base:
                return {"created": False, "reason": "missing_base_branch", "owner": owner, "repo": repo, "head": head}
            if resolved_base == head:
                return {
                    "created": False,
                    "reason": "head_matches_base",
                    "owner": owner,
                    "repo": repo,
                    "head": head,
                    "base": resolved_base,
                }
            existing = client.find_open_pull_request_for_branch(owner, repo, head, base=resolved_base)
            if existing:
                result = {
                    "created": False,
                    "reason": "already_exists",
                    "owner": owner,
                    "repo": repo,
                    "head": head,
                    "base": resolved_base,
                    "pull_request": int(existing.get("number", 0) or 0),
                    "html_url": str(existing.get("html_url", "")).strip(),
                }
            else:
                created = client.create_pull_request(
                    owner,
                    repo,
                    title=title,
                    head=head,
                    base=resolved_base,
                    body=body,
                    draft=draft,
                )
                result = {
                    "created": True,
                    "owner": owner,
                    "repo": repo,
                    "head": head,
                    "base": resolved_base,
                    "pull_request": int(created.get("number", 0) or 0),
                    "html_url": str(created.get("html_url", "")).strip(),
                }
            pull_request_number = int(result.get("pull_request", 0) or 0)
            if auto_merge and pull_request_number > 0:
                result.update(
                    self._attempt_pull_request_merge(
                        client,
                        owner=owner,
                        repo=repo,
                        pull_request=pull_request_number,
                        title=title,
                        merge_method=merge_method,
                    )
                )
            return result
        except GitHubAPIError as exc:
            return {"created": False, "reason": "github_api_error", "error": str(exc)}
