from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.github_api import parse_github_repository_url
from jakal_flow.orchestrator import Orchestrator
from jakal_flow.reporting import Reporter
from jakal_flow.ui_bridge import run_command
from jakal_flow.utils import append_jsonl


def local_temp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_failure_reporting_tests"
    root.mkdir(parents=True, exist_ok=True)
    return root


class TemporaryTestDir:
    def __enter__(self) -> Path:
        self.path = local_temp_root() / f"case_{uuid.uuid4().hex}"
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def fake_codex_snapshot() -> mock.Mock:
    payload = {
        "checked_at": "2026-03-26T00:00:00+00:00",
        "available": True,
        "model_catalog": [],
        "account": {},
        "rate_limits": {"default_limit_id": "codex", "items": []},
        "error": "",
    }
    return mock.Mock(model_catalog=payload["model_catalog"], to_dict=mock.Mock(return_value=payload))


def create_project(workspace_root: Path, repo_dir: Path):
    payload = {
        "project_dir": str(repo_dir),
        "display_name": "Failure Demo",
        "branch": "main",
        "origin_url": "https://github.com/example/failure-demo.git",
        "runtime": {
            "model": "gpt-5.4",
            "effort": "high",
            "test_cmd": "python -m pytest",
            "max_blocks": 2,
        },
    }
    with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
        "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
        side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
    ):
        detail = run_command("save-project-setup", workspace_root, payload)
    orchestrator = Orchestrator(workspace_root)
    project = orchestrator.local_project(repo_dir)
    assert project is not None
    return detail, orchestrator, project


class FailureReportingTests(unittest.TestCase):
    def test_parse_github_repository_url_supports_https_and_ssh(self) -> None:
        self.assertEqual(parse_github_repository_url("https://github.com/example/demo.git"), ("example", "demo"))
        self.assertEqual(parse_github_repository_url("git@github.com:example/demo.git"), ("example", "demo"))
        self.assertIsNone(parse_github_repository_url("https://gitlab.com/example/demo.git"))

    def test_reporter_writes_failure_bundle_and_skips_pr_post_without_token(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            _detail, orchestrator, project = create_project(workspace_root, repo_dir)
            reporter = Reporter(project)

            append_jsonl(
                project.paths.block_log_file,
                {
                    "block_index": 1,
                    "status": "failed",
                    "selected_task": "Investigate failure",
                    "test_summary": "verification failed",
                    "commit_hashes": [],
                },
            )
            append_jsonl(
                project.paths.pass_log_file,
                {
                    "block_index": 1,
                    "pass_type": "block-search-pass",
                    "selected_task": "Investigate failure",
                    "codex_return_code": 1,
                    "rollback_status": "rolled_back_to_safe_revision",
                },
            )
            append_jsonl(
                project.paths.logs_dir / "test_runs.jsonl",
                {
                    "block_index": 1,
                    "label": "block-search-pass",
                    "returncode": 1,
                    "summary": "pytest exited with 1",
                },
            )

            reporter.write_status_report()
            bundle = reporter.write_failure_bundle(
                "block_failed",
                "Search-enabled Codex pass regressed tests and was rolled back.",
                block_index=1,
                selected_task="Investigate failure",
                extra={"conflict": orchestrator._parallel_conflict_details(["src/app.py"])},
            )

            self.assertTrue(Path(bundle["report_json_file"]).exists())
            self.assertTrue(Path(bundle["report_markdown_file"]).exists())
            markdown = Path(bundle["report_markdown_file"]).read_text(encoding="utf-8")
            self.assertIn("jakal-flow failure report", markdown)
            self.assertIn("Conflict Policy", markdown)

            with mock.patch.dict(os.environ, {}, clear=True):
                result = reporter.post_pr_failure_report(bundle)
            self.assertFalse(result["posted"])
            self.assertEqual(result["reason"], "missing_github_token")

    def test_reporter_ensure_pull_request_creates_missing_pull_request(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            _detail, _orchestrator, project = create_project(workspace_root, repo_dir)
            reporter = Reporter(project)

            with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "demo-token"}, clear=True), mock.patch(
                "jakal_flow.reporting.GitHubClient.get_repository",
                return_value=mock.Mock(default_branch="main"),
            ), mock.patch(
                "jakal_flow.reporting.GitHubClient.find_open_pull_request_for_branch",
                return_value=None,
            ) as mocked_find, mock.patch(
                "jakal_flow.reporting.GitHubClient.create_pull_request",
                return_value={"number": 12, "html_url": "https://github.com/example/failure-demo/pull/12"},
            ) as mocked_create:
                result = reporter.ensure_pull_request(
                    head_branch="jakal-flow-lineage-ln2",
                    base_branch="main",
                    title="[ST2] Backend slice",
                    body="demo",
                )

        self.assertTrue(result["created"])
        self.assertEqual(result["pull_request"], 12)
        mocked_find.assert_called_once_with("example", "failure-demo", "jakal-flow-lineage-ln2", base="main")
        mocked_create.assert_called_once()

    def test_reporter_ensure_pull_request_skips_when_head_matches_base(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            _detail, _orchestrator, project = create_project(workspace_root, repo_dir)
            reporter = Reporter(project)

            with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "demo-token"}, clear=True), mock.patch(
                "jakal_flow.reporting.GitHubClient.get_repository",
                return_value=mock.Mock(default_branch="main"),
            ):
                result = reporter.ensure_pull_request(
                    head_branch="main",
                    title="Closeout",
                )

        self.assertFalse(result["created"])
        self.assertEqual(result["reason"], "head_matches_base")


if __name__ == "__main__":
    unittest.main()
