from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.models import RuntimeOptions
from jakal_flow.workspace import WorkspaceManager


def local_temp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tub"
    root.mkdir(parents=True, exist_ok=True)
    return root


class TemporaryTestDir:
    def __enter__(self) -> Path:
        self.path = local_temp_root() / f"workspace-{uuid.uuid4().hex[:8]}"
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


class WorkspaceManagerTests(unittest.TestCase):
    def test_find_project_by_repo_path_prefers_registry_match(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace = WorkspaceManager(temp_dir / "workspace")
            repo_one = temp_dir / "repo-one"
            repo_two = temp_dir / "repo-two"
            repo_one.mkdir(parents=True, exist_ok=True)
            repo_two.mkdir(parents=True, exist_ok=True)

            workspace.initialize_local_project(repo_one, "main", RuntimeOptions(), display_name="Repo One")
            second = workspace.initialize_local_project(repo_two, "main", RuntimeOptions(), display_name="Repo Two")

            with mock.patch.object(workspace, "load_project_by_id", wraps=workspace.load_project_by_id) as load_project_by_id:
                found = workspace.find_project_by_repo_path(repo_two)

        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.metadata.repo_id, second.metadata.repo_id)
        self.assertEqual(load_project_by_id.call_count, 1)
        self.assertEqual(load_project_by_id.call_args.args[0], second.metadata.repo_id)

    def test_find_project_by_repo_path_falls_back_when_registry_repo_path_is_stale(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace = WorkspaceManager(temp_dir / "workspace")
            repo_one = temp_dir / "repo-one"
            repo_two = temp_dir / "repo-two"
            repo_one.mkdir(parents=True, exist_ok=True)
            repo_two.mkdir(parents=True, exist_ok=True)

            first = workspace.initialize_local_project(repo_one, "main", RuntimeOptions(), display_name="Repo One")
            second = workspace.initialize_local_project(repo_two, "main", RuntimeOptions(), display_name="Repo Two")

            registry = json.loads(workspace.registry_file.read_text(encoding="utf-8"))
            registry["projects"][second.metadata.repo_id]["repo_path"] = str(temp_dir / "stale-repo-two")
            workspace.registry_file.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")

            with mock.patch.object(workspace, "load_project_by_id", wraps=workspace.load_project_by_id) as load_project_by_id:
                found = workspace.find_project_by_repo_path(repo_two)

        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.metadata.repo_id, second.metadata.repo_id)
        self.assertEqual(load_project_by_id.call_count, 2)
        self.assertEqual(load_project_by_id.call_args.args[0], second.metadata.repo_id)
        self.assertNotEqual(first.metadata.repo_id, second.metadata.repo_id)


if __name__ == "__main__":
    unittest.main()
