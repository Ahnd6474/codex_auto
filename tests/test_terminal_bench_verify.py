from pathlib import Path

from jakal_flow.terminal_bench_verify import infer_test_command


def test_infer_test_command_prefers_make_test(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("test:\n\tpytest -q\n", encoding="utf-8")
    assert infer_test_command(tmp_path) == "make test"


def test_infer_test_command_detects_pytest_project(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    assert infer_test_command(tmp_path) == "pytest -q"


def test_infer_test_command_detects_go_repo(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")
    assert infer_test_command(tmp_path) == "go test ./..."
