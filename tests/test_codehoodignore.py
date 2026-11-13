"""
Inside a codehood course, `chalk init` and `chalk quiz create` list their paths in
.codehoodignore, so `codehood push` skips them.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from chalk.cli import app
from chalk.codehood import add_codehoodignore


def _course(root: Path) -> None:
    (root / "codehood.toml").write_text('[course]\nname = "x"\n')


def test_helper_without_codehood_toml_creates_nothing(tmp_path: Path) -> None:
    assert add_codehoodignore(tmp_path, "chalk.toml") is False
    assert not (tmp_path / ".codehoodignore").exists()


def test_helper_creates_file_when_missing(tmp_path: Path) -> None:
    _course(tmp_path)
    assert add_codehoodignore(tmp_path, "chalk.toml") is True
    assert (tmp_path / ".codehoodignore").read_text() == "chalk.toml\n"


def test_helper_does_not_duplicate_entries(tmp_path: Path) -> None:
    _course(tmp_path)
    (tmp_path / ".codehoodignore").write_text("  chalk.toml  \n")
    assert add_codehoodignore(tmp_path, "chalk.toml") is False
    assert (tmp_path / ".codehoodignore").read_text() == "  chalk.toml  \n"


def test_helper_keeps_content_and_adds_missing_newline(tmp_path: Path) -> None:
    _course(tmp_path)
    existing = "# private files\n*.pyc\nexams/answers/"
    (tmp_path / ".codehoodignore").write_text(existing)

    assert add_codehoodignore(tmp_path, "p1/") is True
    assert (tmp_path / ".codehoodignore").read_text() == existing + "\np1/\n"


def test_init_adds_chalk_toml_only_inside_codehood_course(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["init", "-c", "turma", "--teacher", "Prof"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / ".codehoodignore").exists()


def test_init_in_codehood_course_writes_ignore_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _course(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["init", "-c", "turma", "--teacher", "Prof"])
    assert result.exit_code == 0, result.output
    assert ".codehoodignore" in result.output
    assert (tmp_path / ".codehoodignore").read_text() == "chalk.toml\n"


def test_quiz_create_adds_quiz_directory_inside_codehood_course(classroom: Path) -> None:
    result = CliRunner().invoke(app, ["quiz", "create", "pz", "--name", "PZ", "--questions", "1"])
    assert result.exit_code == 0, result.output
    assert not (classroom / ".codehoodignore").exists()

    _course(classroom)
    (classroom / ".codehoodignore").write_text("# notes\nchalk.toml\n")
    result = CliRunner().invoke(app, ["quiz", "create", "pz2", "--name", "PZ2", "--questions", "1"])
    assert result.exit_code == 0, result.output
    assert (classroom / ".codehoodignore").read_text() == "# notes\nchalk.toml\npz2/\n"
