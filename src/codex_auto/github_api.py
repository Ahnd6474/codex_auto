from __future__ import annotations

import json
import time
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

    def start_device_flow(self, client_id: str, scope: str = "repo read:user") -> dict:
        payload = urllib.parse.urlencode(
            {
                "client_id": client_id.strip(),
                "scope": scope,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://github.com/login/device/code",
            data=payload,
            headers={
                "Accept": "application/json",
                "User-Agent": "codex-auto",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GitHubAPIError(f"디바이스 로그인 시작 실패: HTTP {exc.code}\n{body}") from exc
        except urllib.error.URLError as exc:
            raise GitHubAPIError(f"디바이스 로그인 연결 실패: {exc.reason}") from exc

    def poll_device_flow(self, client_id: str, device_code: str, interval: int, timeout_seconds: int) -> str:
        deadline = time.time() + timeout_seconds
        wait_seconds = max(1, interval)
        while time.time() < deadline:
            payload = urllib.parse.urlencode(
                {
                    "client_id": client_id.strip(),
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                "https://github.com/login/oauth/access_token",
                data=payload,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "codex-auto",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise GitHubAPIError(f"디바이스 로그인 토큰 조회 실패: HTTP {exc.code}\n{body}") from exc
            except urllib.error.URLError as exc:
                raise GitHubAPIError(f"디바이스 로그인 연결 실패: {exc.reason}") from exc

            if "access_token" in data:
                return str(data["access_token"])

            error = data.get("error", "")
            if error == "authorization_pending":
                time.sleep(wait_seconds)
                continue
            if error == "slow_down":
                wait_seconds += 5
                time.sleep(wait_seconds)
                continue
            if error in {"expired_token", "token_expired"}:
                raise GitHubAPIError("디바이스 인증 코드가 만료되었습니다. 다시 로그인하세요.")
            if error == "access_denied":
                raise GitHubAPIError("GitHub 로그인 승인이 취소되었습니다.")
            if error == "device_flow_disabled":
                raise GitHubAPIError("이 OAuth 앱은 Device Flow가 활성화되어 있지 않습니다.")
            if error == "incorrect_client_credentials":
                raise GitHubAPIError("GitHub OAuth Client ID가 잘못되었거나 앱 설정이 올바르지 않습니다.")
            if error:
                raise GitHubAPIError(f"디바이스 로그인 실패: {error}")
            time.sleep(wait_seconds)
        raise GitHubAPIError("GitHub 로그인 대기 시간이 초과되었습니다.")

    def build_authorize_url(self, client_id: str, redirect_uri: str, state: str, scope: str = "repo read:user") -> str:
        query = urllib.parse.urlencode(
            {
                "client_id": client_id.strip(),
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
                "prompt": "select_account",
            }
        )
        return f"https://github.com/login/oauth/authorize?{query}"

    def exchange_web_flow_code(
        self,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
    ) -> str:
        payload = urllib.parse.urlencode(
            {
                "client_id": client_id.strip(),
                "client_secret": client_secret.strip(),
                "code": code,
                "redirect_uri": redirect_uri,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://github.com/login/oauth/access_token",
            data=payload,
            headers={
                "Accept": "application/json",
                "User-Agent": "codex-auto",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GitHubAPIError(f"OAuth 토큰 교환 실패: HTTP {exc.code}\n{body}") from exc
        except urllib.error.URLError as exc:
            raise GitHubAPIError(f"OAuth 토큰 교환 연결 실패: {exc.reason}") from exc

        access_token = data.get("access_token")
        if access_token:
            return str(access_token)
        error = data.get("error", "unknown_error")
        raise GitHubAPIError(f"OAuth 토큰 교환 실패: {error}")
