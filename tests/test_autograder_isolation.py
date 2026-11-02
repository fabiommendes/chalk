import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from chalk.autograder.repo import Repo
from chalk.autograder.script_grader import ScriptGrader
from chalk.autograder.script_runner import ChalkEnv, ScriptRunner
from chalk.core import models


def run_script(tmp_path: Path, body: str, *, timeout: float = 5, **env_kwargs):
    script = tmp_path / "grade.sh"
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    env = ChalkEnv(
        answer="x",
        answer_path="answer.txt",
        question_id="q1",
        quiz_id="p1",
        student_id="s1",
        **env_kwargs,
    )
    return ScriptRunner(script, Repo(work), env=env, timeout=timeout).run(), work


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); check its state.
    try:
        state = Path(f"/proc/{pid}/stat").read_text().split()[2]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state != "Z"


def wait_dead(pid: int) -> bool:
    for _ in range(40):
        if not is_alive(pid):
            return True
        time.sleep(0.05)
    return False


class TestEnvironment:
    def test_secrets_are_not_passed(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "secret")
        _, work = run_script(tmp_path, 'env > env.txt\necho 1 > "$CHALK_RESULT"\n')
        env = (work / "env.txt").read_text()
        assert "GITHUB_TOKEN" not in env
        assert "PATH=" in env
        assert "CHALK_STUDENT=s1" in env

    def test_pass_env_adds_variables(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("MY_SERVER", "localhost:8000")
        _, work = run_script(
            tmp_path, 'env > env.txt\necho 1 > "$CHALK_RESULT"\n', pass_env=("MY_SERVER",)
        )
        assert "MY_SERVER=localhost:8000" in (work / "env.txt").read_text()


class TestProcessTree:
    def test_timeout_kills_children(self, tmp_path) -> None:
        result, work = run_script(
            tmp_path, "sleep 30 &\necho $! > child.pid\nsleep 30\n", timeout=0.5
        )
        assert not result
        assert wait_dead(int((work / "child.pid").read_text()))

    def test_background_processes_die_after_exit(self, tmp_path) -> None:
        _, work = run_script(
            tmp_path, 'sleep 30 &\necho $! > child.pid\necho 1 > "$CHALK_RESULT"\n'
        )
        assert wait_dead(int((work / "child.pid").read_text()))


class TestTemplate:
    def test_student_code_cannot_change_template(self, tmp_path) -> None:
        template = tmp_path / "template"
        (template / "tests").mkdir(parents=True)
        test_file = template / "tests" / "test_x.py"
        test_file.write_text("original")

        question = SimpleNamespace(
            id="q1",
            quiz=SimpleNamespace(id="p1"),
            get_template_path=lambda: template,
        )
        grader = ScriptGrader(tmp_path / "grade.sh", question, models.Autograder())  # type: ignore[arg-type]
        with grader.student_repository("s1", "answer") as repo:
            (repo.root / "tests" / "test_x.py").write_text("hacked")

        assert test_file.read_text() == "original"


@pytest.fixture(autouse=True)
def _linux_only() -> None:
    if not Path("/proc/self").exists():
        pytest.skip("needs /proc")
