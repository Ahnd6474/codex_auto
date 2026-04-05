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
    def test_registry_persists_workspace_relative_project_root_and_supports_workspace_move(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            workspace = WorkspaceManager(workspace_root)

            context = workspace.initialize_local_project(repo_dir, "main", RuntimeOptions(), display_name="Repo")
            registry = json.loads(workspace.registry_file.read_text(encoding="utf-8"))
            item = registry["projects"][context.metadata.repo_id]

            self.assertEqual(
                item["project_root_relative"],
                f"projects/{context.metadata.slug}",
            )

            moved_workspace_root = temp_dir / "workspace-moved"
            shutil.copytree(workspace_root, moved_workspace_root)
            moved_workspace = WorkspaceManager(moved_workspace_root)

            moved = moved_workspace.load_project_by_id(context.metadata.repo_id)

            self.assertEqual(
                moved.paths.project_root.resolve(),
                (moved_workspace_root / "projects" / context.metadata.slug).resolve(),
            )

    def test_local_project_falls_back_to_workspace_logs_when_repo_path_is_unavailable(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace = WorkspaceManager(temp_dir / "workspace")
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            created = workspace.initialize_local_project(repo_dir, "main", RuntimeOptions(), display_name="Repo")
            stale_repo = temp_dir / "stale-repo"
            metadata = json.loads(created.paths.metadata_file.read_text(encoding="utf-8"))
            metadata["repo_path"] = str(stale_repo)
            created.paths.metadata_file.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
            registry = json.loads(workspace.registry_file.read_text(encoding="utf-8"))
            registry["projects"][created.metadata.repo_id]["repo_path"] = str(stale_repo)
            workspace.registry_file.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")

            loaded = workspace.load_project_by_id(created.metadata.repo_id)

            self.assertEqual(loaded.metadata.repo_id, created.metadata.repo_id)
            self.assertEqual(loaded.paths.logs_dir.resolve(), (loaded.paths.project_root / "logs").resolve())
            self.assertEqual(loaded.paths.block_log_file.resolve(), (loaded.paths.project_root / "logs" / "blocks.jsonl").resolve())
            self.assertEqual(loaded.metadata.repo_path, stale_repo.resolve())

    def test_rebind_local_project_repo_path_updates_existing_entry(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace = WorkspaceManager(temp_dir / "workspace")
            original_repo = temp_dir / "repo-one"
            rebound_repo = temp_dir / "repo-two"
            original_repo.mkdir(parents=True, exist_ok=True)
            rebound_repo.mkdir(parents=True, exist_ok=True)

            created = workspace.initialize_local_project(original_repo, "main", RuntimeOptions(), display_name="Repo")
            rebound = workspace.rebind_local_project_repo_path(workspace.load_project_by_id(created.metadata.repo_id), rebound_repo)
            registry = json.loads(workspace.registry_file.read_text(encoding="utf-8"))

            self.assertEqual(rebound.metadata.repo_path, rebound_repo.resolve())
            self.assertEqual(rebound.paths.repo_dir, rebound_repo.resolve())
            self.assertEqual(registry["projects"][created.metadata.repo_id]["repo_path"], str(rebound_repo.resolve()))
            found = workspace.find_project_by_repo_path(rebound_repo)
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found.metadata.repo_id, created.metadata.repo_id)

    def test_list_projects_skips_inaccessible_registry_entries(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace = WorkspaceManager(temp_dir / "workspace")
            repo_one = temp_dir / "repo-one"
            repo_two = temp_dir / "repo-two"
            repo_one.mkdir(parents=True, exist_ok=True)
            repo_two.mkdir(parents=True, exist_ok=True)

            first = workspace.initialize_local_project(repo_one, "main", RuntimeOptions(), display_name="Repo One")
            second = workspace.initialize_local_project(repo_two, "main", RuntimeOptions(), display_name="Repo Two")
            original_load = workspace.load_project_by_id

            def guarded_load(repo_id: str):
                if repo_id == first.metadata.repo_id:
                    raise PermissionError("access denied to stale project path")
                return original_load(repo_id)

            with mock.patch.object(workspace, "load_project_by_id", side_effect=guarded_load):
                projects = workspace.list_projects()

            self.assertEqual([project.metadata.repo_id for project in projects], [second.metadata.repo_id])
            skip_lines = workspace.registry_skip_log_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(skip_lines), 1)
            skip_entry = json.loads(skip_lines[0])
            self.assertEqual(skip_entry["entry_id"], first.metadata.repo_id)
            self.assertEqual(skip_entry["registry_section"], "projects")
            self.assertEqual(skip_entry["error_type"], "PermissionError")

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
        self.assertGreaterEqual(load_project_by_id.call_count, 1)
        self.assertTrue(
            any(call.args[0] == second.metadata.repo_id for call in load_project_by_id.call_args_list)
        )
        self.assertNotEqual(first.metadata.repo_id, second.metadata.repo_id)

    def test_find_project_by_repo_path_skips_inaccessible_projects_during_fallback_scan(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace = WorkspaceManager(temp_dir / "workspace")
            repo_one = temp_dir / "repo-one"
            repo_two = temp_dir / "repo-two"
            repo_one.mkdir(parents=True, exist_ok=True)
            repo_two.mkdir(parents=True, exist_ok=True)

            first = workspace.initialize_local_project(repo_one, "main", RuntimeOptions(), display_name="Repo One")
            second = workspace.initialize_local_project(repo_two, "main", RuntimeOptions(), display_name="Repo Two")
            broken, target = sorted(
                [first, second],
                key=lambda project: project.metadata.repo_id,
            )
            registry = json.loads(workspace.registry_file.read_text(encoding="utf-8"))
            registry["projects"][broken.metadata.repo_id]["repo_path"] = str(target.metadata.repo_path)
            registry["projects"][target.metadata.repo_id]["repo_path"] = str(temp_dir / "stale-target-repo")
            workspace.registry_file.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
            original_load = workspace.load_project_by_id

            def guarded_load(repo_id: str):
                if repo_id == broken.metadata.repo_id:
                    raise PermissionError("access denied to stale project path")
                return original_load(repo_id)

            with mock.patch.object(workspace, "load_project_by_id", side_effect=guarded_load):
                with mock.patch.object(workspace, "_record_registry_skip", wraps=workspace._record_registry_skip) as record_skip:
                    found = workspace.find_project_by_repo_path(target.metadata.repo_path)

        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.metadata.repo_id, target.metadata.repo_id)
        self.assertGreaterEqual(record_skip.call_count, 1)
        self.assertEqual(record_skip.call_args_list[0].args[0], "projects")
        self.assertEqual(record_skip.call_args_list[0].args[1], broken.metadata.repo_id)
        self.assertIsInstance(record_skip.call_args_list[0].args[2], PermissionError)


if __name__ == "__main__":
    unittest.main()
