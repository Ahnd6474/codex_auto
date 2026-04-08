from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.git_ops import GitOps, GitCommandError
from jakal_flow.lit_ops import LitCommandError, LitOps
from jakal_flow.models import ExecutionPlanState, RuntimeOptions
from jakal_flow.orchestrator import Orchestrator
from jakal_flow.runtime_config import normalize_runtime_payload


class RuntimeConfigLitTests(unittest.TestCase):
    def test_normalize_runtime_payload_accepts_lit_backend(self) -> None:
        payload = normalize_runtime_payload({"repo_backend": "LiT"})
        self.assertEqual(payload["repo_backend"], "lit")


class GitOpsLitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="jakal-flow-lit-gitops-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _prepare_lit_repo(self) -> Path:
        repo_dir = self.temp_dir / "repo"
        (repo_dir / ".lit" / "refs" / "heads").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".lit" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (repo_dir / ".lit" / "refs" / "heads" / "main").write_text("old-revision\n", encoding="utf-8")
        (repo_dir / ".lit" / "state").mkdir(parents=True, exist_ok=True)
        return repo_dir

    def test_hard_reset_rewinds_lit_branch_head(self) -> None:
        repo_dir = self._prepare_lit_repo()
        ops = GitOps()

        with mock.patch(
            "jakal_flow.lit_ops.run_subprocess",
            return_value=subprocess.CompletedProcess(
                ["lit", "restore", "--source", "new-revision"],
                0,
                stdout="restored 1 path(s) from new-revision\n",
                stderr="",
            ),
        ) as run_subprocess_mock:
            ops.hard_reset(repo_dir, "new-revision")

        self.assertEqual(
            (repo_dir / ".lit" / "refs" / "heads" / "main").read_text(encoding="utf-8"),
            "new-revision\n",
        )
        self.assertEqual(
            run_subprocess_mock.call_args.kwargs["cwd"],
            repo_dir,
        )
        self.assertEqual(
            run_subprocess_mock.call_args.args[0],
            ["lit", "restore", "--source", "new-revision"],
        )

    def test_changed_files_parses_lit_status_output(self) -> None:
        repo_dir = self._prepare_lit_repo()
        ops = GitOps()
        status_output = "\n".join(
            [
                "Changes to be committed:",
                "  added: src/app.py",
                "  modified: README.md",
                "Changes not staged for commit:",
                "  deleted: stale.txt",
                "Untracked files:",
                "  notes.txt",
                "",
            ]
        )
        with mock.patch(
            "jakal_flow.lit_ops.run_subprocess",
            return_value=subprocess.CompletedProcess(
                ["lit", "status"],
                0,
                stdout=status_output,
                stderr="",
            ),
        ):
            changed = ops.changed_files(repo_dir)

        self.assertEqual(changed, ["src/app.py", "README.md", "stale.txt", "notes.txt"])

    def test_lit_run_falls_back_to_python_module_when_script_is_missing(self) -> None:
        repo_dir = self._prepare_lit_repo()
        ops = LitOps()

        with mock.patch("jakal_flow.lit_ops.importlib.util.find_spec", return_value=object()), mock.patch(
            "jakal_flow.lit_ops.run_subprocess",
            side_effect=[
                FileNotFoundError("missing lit"),
                subprocess.CompletedProcess(
                    [sys.executable, "-m", "lit", "status"],
                    0,
                    stdout="nothing to commit, working tree clean\n",
                    stderr="",
                ),
            ],
        ) as run_subprocess_mock:
            result = ops.run(["status"], cwd=repo_dir)

        self.assertEqual(result.command, [sys.executable, "-m", "lit", "status"])
        self.assertEqual(run_subprocess_mock.call_args_list[0].args[0], ["lit", "status"])
        self.assertEqual(run_subprocess_mock.call_args_list[1].args[0], [sys.executable, "-m", "lit", "status"])

    def test_lit_run_wraps_missing_executable_as_lit_command_error(self) -> None:
        repo_dir = self._prepare_lit_repo()
        ops = LitOps(command="lit-missing")

        with mock.patch("jakal_flow.lit_ops.run_subprocess", side_effect=FileNotFoundError("missing lit")):
            with self.assertRaisesRegex(LitCommandError, "jakal-lit"):
                ops.run(["status"], cwd=repo_dir)


class OrchestratorLitSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="jakal-flow-lit-orchestrator-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_setup_local_project_uses_lit_backend(self) -> None:
        workspace_root = self.temp_dir / "workspace"
        repo_dir = self.temp_dir / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(repo_backend="lit")

        with mock.patch.object(orchestrator.git, "ensure_repository", return_value=True) as ensure_repo, mock.patch.object(
            orchestrator.git,
            "current_branch",
            return_value="main",
        ), mock.patch.object(orchestrator.git, "configure_local_identity"), mock.patch.object(
            orchestrator.git,
            "has_commits",
            return_value=False,
        ), mock.patch.object(
            orchestrator.git,
            "create_initial_commit",
            return_value="lit-revision-1",
        ), mock.patch.object(
            orchestrator.git,
            "remote_url",
            return_value=None,
        ), mock.patch(
            "jakal_flow.orchestrator.ensure_virtualenv"
        ), mock.patch(
            "jakal_flow.orchestrator.ensure_gitignore",
            return_value=True,
        ), mock.patch.object(
            orchestrator,
            "_ensure_project_documents",
        ), mock.patch.object(
            orchestrator,
            "load_execution_plan_state",
            return_value=ExecutionPlanState(default_test_command=runtime.test_cmd),
        ), mock.patch.object(
            orchestrator,
            "save_execution_plan_state",
            side_effect=lambda context, state: state,
        ):
            context = orchestrator.setup_local_project(
                project_dir=repo_dir,
                runtime=runtime,
                branch="main",
                origin_url="https://example.com/lit-upstream",
            )

        ensure_repo.assert_called_once_with(repo_dir.resolve(), "main", backend="lit")
        self.assertEqual(context.metadata.vcs_backend, "lit")
        self.assertEqual(context.metadata.current_safe_revision, "lit-revision-1")
        self.assertEqual(context.metadata.origin_url, "https://example.com/lit-upstream")
        self.assertEqual(context.runtime.repo_backend, "lit")

    def test_resolve_local_repo_backend_prefers_git_when_present(self) -> None:
        workspace_root = self.temp_dir / "workspace-git"
        repo_dir = self.temp_dir / "repo-git"
        (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".lit").mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)

        backend = orchestrator._resolve_local_repo_backend(repo_dir, preferred="auto")

        self.assertEqual(backend, "git")

    def test_resolve_local_repo_backend_defaults_to_git_for_new_local_dirs(self) -> None:
        workspace_root = self.temp_dir / "workspace-auto"
        repo_dir = self.temp_dir / "repo-auto"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)

        backend = orchestrator._resolve_local_repo_backend(repo_dir, preferred="auto")

        self.assertEqual(backend, "git")

    def test_resolve_local_repo_backend_honors_explicit_lit_for_new_local_dirs(self) -> None:
        workspace_root = self.temp_dir / "workspace-auto-lit"
        repo_dir = self.temp_dir / "repo-auto-lit"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)

        backend = orchestrator._resolve_local_repo_backend(repo_dir, preferred="lit")

        self.assertEqual(backend, "lit")

    def test_resolve_local_repo_backend_prefers_actual_git_repo_over_stale_lit_preference(self) -> None:
        workspace_root = self.temp_dir / "workspace-prefer-actual"
        repo_dir = self.temp_dir / "repo-prefer-actual"
        (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)

        backend = orchestrator._resolve_local_repo_backend(repo_dir, preferred="lit")

        self.assertEqual(backend, "git")


if __name__ == "__main__":
    unittest.main()
