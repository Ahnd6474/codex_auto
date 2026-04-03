from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow import desktop_runtime_bundle


class DesktopRuntimeBundleTests(unittest.TestCase):
    def test_parse_shim_target_extracts_package_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            shim_path = Path(temp_dir) / "codex.cmd"
            shim_path.write_text(
                '@ECHO off\n"%_prog%"  "%dp0%\\node_modules\\@openai\\codex\\bin\\codex.js" %*\n',
                encoding="utf-8",
            )

            parsed = desktop_runtime_bundle._parse_shim_target(shim_path)

        self.assertIsNotNone(parsed)
        relative_target, package_root = parsed or (Path(), Path())
        self.assertEqual(relative_target.as_posix(), "node_modules/@openai/codex/bin/codex.js")
        self.assertEqual(package_root.as_posix(), "node_modules/@openai/codex")

    def test_bundle_tool_command_copies_node_shim_and_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            npm_root = root / "npm"
            target_dir = root / "bundle"
            package_dir = npm_root / "node_modules" / "@openai" / "codex"
            package_dir.mkdir(parents=True)
            (package_dir / "package.json").write_text('{"name":"@openai/codex","version":"1.2.3"}', encoding="utf-8")
            (package_dir / "bin").mkdir()
            (package_dir / "bin" / "codex.js").write_text("console.log('codex');\n", encoding="utf-8")
            (npm_root / "codex.cmd").write_text(
                '@ECHO off\n"%_prog%"  "%dp0%\\node_modules\\@openai\\codex\\bin\\codex.js" %*\n',
                encoding="utf-8",
            )
            (root / "node.exe").write_text("node-binary", encoding="utf-8")

            original_npm_root = desktop_runtime_bundle._resolve_global_npm_root
            original_which = desktop_runtime_bundle.shutil.which
            try:
                desktop_runtime_bundle._resolve_global_npm_root = lambda: npm_root
                desktop_runtime_bundle.shutil.which = lambda command: str(root / "node.exe") if command == "node" else None

                manifest = desktop_runtime_bundle._bundle_tool_command(target_dir, "codex.cmd")
            finally:
                desktop_runtime_bundle._resolve_global_npm_root = original_npm_root
                desktop_runtime_bundle.shutil.which = original_which

            bundled_root = target_dir / "bin"
            self.assertTrue((bundled_root / "node.exe").exists())
            self.assertTrue((bundled_root / "codex.cmd").exists())
            self.assertTrue((bundled_root / "node_modules" / "@openai" / "codex" / "bin" / "codex.js").exists())
            self.assertTrue(manifest.available)
            self.assertEqual(manifest.package_name, "@openai/codex")
            self.assertEqual(manifest.package_version, "1.2.3")

    def test_remove_tree_retries_transient_windows_directory_not_empty_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "bundle"
            target.mkdir()
            (target / "placeholder.txt").write_text("data", encoding="utf-8")

            attempt_state = {"count": 0}
            original_rmtree = desktop_runtime_bundle.shutil.rmtree
            original_sleep = desktop_runtime_bundle.time.sleep

            def flaky_rmtree(path, onerror=None):
                attempt_state["count"] += 1
                if attempt_state["count"] < 4:
                    exc = OSError(145, "directory is not empty")
                    exc.winerror = 145
                    raise exc
                return original_rmtree(path, onerror=onerror)

            try:
                desktop_runtime_bundle.shutil.rmtree = flaky_rmtree
                desktop_runtime_bundle.time.sleep = lambda _: None
                desktop_runtime_bundle._remove_tree(target)
            finally:
                desktop_runtime_bundle.shutil.rmtree = original_rmtree
                desktop_runtime_bundle.time.sleep = original_sleep

            self.assertEqual(attempt_state["count"], 4)
            self.assertFalse(target.exists())

    def test_bundle_runtime_can_skip_tool_bundling(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir) / "bundle"
            original_bundle_python_runtime = desktop_runtime_bundle._bundle_python_runtime
            original_bundle_tool_command = desktop_runtime_bundle._bundle_tool_command
            tool_calls: list[str] = []

            def fake_bundle_python_runtime(target: Path):
                python_home = target / "py"
                python_home.mkdir(parents=True, exist_ok=True)
                executable = python_home / "python.exe"
                executable.write_text("", encoding="utf-8")
                return desktop_runtime_bundle.BundledPythonManifest(
                    executable=str(executable),
                    home=str(python_home),
                    version="3.12.0",
                )

            def fake_bundle_tool_command(target: Path, command_name: str):
                tool_calls.append(command_name)
                return desktop_runtime_bundle.BundledToolManifest(
                    command=command_name,
                    available=True,
                    bundled_command="",
                    package_name="",
                    package_version="",
                    source_command="",
                    reason="",
                )

            try:
                desktop_runtime_bundle._bundle_python_runtime = fake_bundle_python_runtime
                desktop_runtime_bundle._bundle_tool_command = fake_bundle_tool_command
                manifest = desktop_runtime_bundle.bundle_runtime(
                    target_dir=target_dir,
                    bundle_tools=False,
                    required_commands=("codex.cmd",),
                    optional_commands=("gemini.cmd",),
                )
            finally:
                desktop_runtime_bundle._bundle_python_runtime = original_bundle_python_runtime
                desktop_runtime_bundle._bundle_tool_command = original_bundle_tool_command

            self.assertEqual(tool_calls, [])
            self.assertEqual(manifest.tools, [])
            self.assertTrue((target_dir / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
