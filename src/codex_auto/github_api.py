from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class GitHubAPIError(RuntimeError):
    pass


@dataclass(slots=True)
class GitHubRepository:
    name: str
    full_name: str
    html_url: str
    clone_url: str
    default_branch: str
    description: str
    private: bool
    stars: int

    def to_display_row(self) -> tuple[str, str, str, str]:
        return (
            self.full_name,
            self.default_branch,
            "비공개" if self.private else "공개",
            str(self.stars),
        )


class GitHubClient:
    def __init__(self, token: str = "") -> None:
        self.token = token.strip()

    def _request_json(self, url: str) -> dict | list:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "codex-auto",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GitHubAPIError(f"GitHub API 요청 실패: HTTP {exc.code}\n{body}") from exc
        except urllib.error.URLError as exc:
            raise GitHubAPIError(f"GitHub API 연결 실패: {exc.reason}") from exc

    def search_repositories(self, query: str, per_page: int = 20) -> list[GitHubRepository]:
        if not query.strip():
            return []
        encoded = urllib.parse.quote(query.strip())
        url = f"https://api.github.com/search/repositories?q={encoded}&sort=stars&order=desc&per_page={per_page}"
        payload = self._request_json(url)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return [self._parse_repo(item) for item in items]

    def list_my_repositories(self, per_page: int = 100) -> list[GitHubRepository]:
        if not self.token:
            raise GitHubAPIError("내 저장소 조회에는 GitHub Personal Access Token 이 필요합니다.")
        url = f"https://api.github.com/user/repos?sort=updated&per_page={per_page}"
        payload = self._request_json(url)
        items = payload if isinstance(payload, list) else []
        return [self._parse_repo(item) for item in items]

    def _parse_repo(self, item: dict) -> GitHubRepository:
        return GitHubRepository(
            name=item.get("name", ""),
            full_name=item.get("full_name", ""),
            html_url=item.get("html_url", ""),
            clone_url=item.get("clone_url", ""),
            default_branch=item.get("default_branch", "main"),
            description=item.get("description") or "",
            private=bool(item.get("private", False)),
            stars=int(item.get("stargazers_count", 0)),
        )
