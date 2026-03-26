from __future__ import annotations

import os
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

from .github_api import GitHubAPIError, GitHubClient, parse_github_repository_url
from .models import ProjectContext, TestRunResult
from .utils import append_jsonl, append_text, compact_text, now_utc_iso, read_json, read_jsonl_tail, read_text, write_json, write_text


class Reporter:
    def __init__(self, context: ProjectContext) -> None:
        self.context = context

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
        generated_at = now_utc_iso()
        safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in failure_type.strip().lower())
        safe_name = safe_name.strip("-") or "failure"
        stem = f"{generated_at.replace(':', '').replace('-', '').replace('+', '').replace('T', 't')}_{safe_name}"
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
            "extra": extra or {},
        }
        json_path = self.context.paths.reports_dir / f"{stem}.pr_failure.json"
        md_path = self.context.paths.reports_dir / f"{stem}.pr_failure.md"
        write_json(json_path, payload)
        write_text(md_path, self.format_pr_failure_report(payload))
        payload["report_json_file"] = str(json_path)
        payload["report_markdown_file"] = str(md_path)
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
        token = (
            os.environ.get("JAKAL_FLOW_GITHUB_TOKEN", "").strip()
            or os.environ.get("GITHUB_TOKEN", "").strip()
            or os.environ.get("GH_TOKEN", "").strip()
        )
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
