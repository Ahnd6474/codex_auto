from __future__ import annotations

import heapq

from .models import MemoryEntry, ProjectPaths
from .utils import append_jsonl, now_utc_iso, read_jsonl, similarity_score


class MemoryStore:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    def record_success(
        self,
        task: str,
        summary: str,
        tags: list[str],
        block_index: int,
        commit_hash: str | None,
    ) -> None:
        entry = MemoryEntry(
            timestamp=now_utc_iso(),
            task=task,
            summary=summary,
            tags=tags,
            block_index=block_index,
            commit_hash=commit_hash,
        )
        append_jsonl(self.paths.success_patterns_file, entry.to_dict())

    def record_failure(
        self,
        task: str,
        summary: str,
        tags: list[str],
        block_index: int,
        commit_hash: str | None,
    ) -> None:
        entry = MemoryEntry(
            timestamp=now_utc_iso(),
            task=task,
            summary=summary,
            tags=tags,
            block_index=block_index,
            commit_hash=commit_hash,
        )
        append_jsonl(self.paths.failure_patterns_file, entry.to_dict())

    def record_task_summary(
        self,
        task: str,
        summary: str,
        tags: list[str],
        block_index: int,
        commit_hash: str | None,
    ) -> None:
        entry = MemoryEntry(
            timestamp=now_utc_iso(),
            task=task,
            summary=summary,
            tags=tags,
            block_index=block_index,
            commit_hash=commit_hash,
        )
        append_jsonl(self.paths.task_summaries_file, entry.to_dict())

    def retrieve(self, query: str, limit: int = 5) -> list[dict]:
        if limit <= 0:
            return []
        top_matches: list[tuple[float, str, str, dict]] = []
        for file_path, label in [
            (self.paths.success_patterns_file, "success"),
            (self.paths.failure_patterns_file, "failure"),
            (self.paths.task_summaries_file, "summary"),
        ]:
            for item in read_jsonl(file_path):
                text = f"{item.get('task', '')} {item.get('summary', '')} {' '.join(item.get('tags', []))}"
                score = similarity_score(query, text)
                if score > 0:
                    candidate = (score, item.get("timestamp", ""), label, item)
                    if len(top_matches) < limit:
                        heapq.heappush(top_matches, candidate)
                    else:
                        heapq.heappushpop(top_matches, candidate)
        top_matches.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [{**item, "memory_type": label, "similarity": score} for score, _, label, item in top_matches]

    def render_context(self, query: str, limit: int = 5) -> str:
        entries = self.retrieve(query, limit=limit)
        if not entries:
            return "No strongly relevant prior memory found."
        lines = ["Relevant prior memory:"]
        for item in entries:
            lines.append(
                f"- [{item['memory_type']}] block {item['block_index']}: {item['task']} :: {item['summary']}"
            )
        return "\n".join(lines)
