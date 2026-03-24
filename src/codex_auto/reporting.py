from __future__ import annotations

from pathlib import Path

from .models import ProjectContext, TestRunResult
from .utils import append_jsonl, append_text, now_utc_iso, read_jsonl, write_json, write_text


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
        passes = read_jsonl(self.context.paths.pass_log_file)[-20:]
        blocks = read_jsonl(self.context.paths.block_log_file)[-20:]
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

    def render_history(self, limit: int = 10) -> str:
        entries = read_jsonl(self.context.paths.block_log_file)[-limit:]
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
