from __future__ import annotations

import os
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

from .contract_wave import load_lineage_manifest_payloads
from .failure_logs import collect_failure_artifacts
from .github_api import GitHubAPIError, GitHubClient, parse_github_repository_url
from .models import ProjectContext, TestRunResult
from .utils import append_jsonl, append_text, compact_text, now_utc_iso, read_json, read_jsonl_tail, read_text, write_json, write_text


class Reporter:
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
        report = {
            "generated_at": now_utc_iso(),
            "repository": self.context.metadata.to_dict(),
            "loop_state": self.context.loop_state.to_dict(),
            "recent_passes": passes,
            "recent_blocks": blocks,
            "planning_metrics": read_jsonl_tail(self.context.paths.planning_metrics_file, 40),
            "spine": read_json(self.context.paths.spine_file, default={}),
            "common_requirements": read_json(self.context.paths.common_requirements_file, default={}),
            "lineage_manifests": load_lineage_manifest_payloads(self.context.paths),
        }
        path = self.context.paths.reports_dir / "latest_report.json"
        write_json(path, report)
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
                f"block={item['block_index']} status={item['status']} task={item['selected_task']} commits={','.join(item.get('commit_hashes', [])) or 'none'}"
            )
        return "\n".join(lines)

    def save_test_result(self, block_index: int, label: str, result: TestRunResult) -> None:
        payload = result.to_dict()
        payload["block_index"] = block_index
        payload["label"] = label
        append_jsonl(self.context.paths.logs_dir / "test_runs.jsonl", payload)

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
                f"- block={item.get('block_index')} status={item.get('status')} task={item.get('selected_task')} summary={compact_text(str(item.get('test_summary', '')), 180)}"
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
