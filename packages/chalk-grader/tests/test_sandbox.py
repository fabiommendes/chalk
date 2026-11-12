import time
from pathlib import Path

import pytest

from chalk_grader import disqualification as dq
from chalk_grader import models
from chalk_grader.sandbox import BwrapUnavailable, bwrap_command, check_bwrap
from chalk_grader.script_grader import ScriptGrader
from chalk_grader.task import Task


def bwrap_works() -> bool:
    try:
        check_bwrap()
    except BwrapUnavailable:
        return False
    return True


needs_bwrap = pytest.mark.skipif(not bwrap_works(), reason="bwrap cannot create a sandbox here")


def grade(tmp_path: Path, body: str, **conf):
    """
    Run the script body in the sandbox and return the score.
    """
    return run(tmp_path, body, **conf).score


def run(tmp_path: Path, body: str, **conf):
    script = tmp_path / "grade.sh"
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(0o755)
    task = Task("q1", "p1", root=tmp_path, template=None)
    grader = ScriptGrader(script, task, models.Autograder(**conf))
    return grader("s1", "answer")


def report(body: str) -> str:
    """
    Script body that runs the check and writes 1 if it succeeds, 0 otherwise.
    """
    return f'if {body}; then echo 1 > "$CHALK_RESULT"; else echo 0 > "$CHALK_RESULT"; fi\n'


class TestCommand:
    def test_hides_home_and_tmp(self, monkeypatch) -> None:
        monkeypatch.setattr("chalk_grader.sandbox.check_bwrap", lambda: "bwrap")
        args = bwrap_command("true", workdir=Path("/tmp/w"), env={"PATH": ""})
        tmpfs = {args[i + 1] for i, a in enumerate(args) if a == "--tmpfs"}
        assert {"/home", "/tmp", "/run"} <= tmpfs
        assert "--unshare-all" in args
        assert "--share-net" not in args

    def test_hides_home_outside_hidden_dirs(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr("chalk_grader.sandbox.check_bwrap", lambda: "bwrap")
        monkeypatch.setattr("chalk_grader.sandbox.HIDDEN", ())
        args = bwrap_command("true", workdir=Path("/w"), env={"HOME": str(tmp_path)})
        assert args[args.index(str(tmp_path)) - 1] == "--tmpfs"

    def test_reexposes_path_inside_home(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr("chalk_grader.sandbox.check_bwrap", lambda: "bwrap")
        monkeypatch.setattr("chalk_grader.sandbox.HIDDEN", (str(tmp_path),))
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        args = bwrap_command("true", workdir=tmp_path / "w", env={"PATH": str(bin_dir)})
        i = args.index(str(bin_dir))
        assert args[i - 1] == "--ro-bind"

    def test_recreates_symlink_inside_home(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr("chalk_grader.sandbox.check_bwrap", lambda: "bwrap")
        monkeypatch.setattr("chalk_grader.sandbox.HIDDEN", (str(tmp_path),))
        (tmp_path / "python-3.13.5").mkdir()
        (tmp_path / "python-3.13").symlink_to("python-3.13.5")
        args = bwrap_command(
            "true", workdir=Path("/w"), readable=[tmp_path / "python-3.13"], env={}
        )
        i = args.index("--symlink")
        assert args[i + 1 : i + 3] == ["python-3.13.5", str(tmp_path / "python-3.13")]
        assert args[args.index(str(tmp_path / "python-3.13.5")) - 1] == "--ro-bind"

    def test_overlays_come_after_workdir(self, monkeypatch) -> None:
        monkeypatch.setattr("chalk_grader.sandbox.check_bwrap", lambda: "bwrap")
        args = bwrap_command(
            "true", workdir=Path("/w"), overlays=[(Path("/t/tests"), Path("/w/tests"))], env={}
        )
        assert args.index("/w/tests") > args.index("--bind")
        assert args[args.index("/w/tests") - 2] == "--ro-bind"

    def test_network(self, monkeypatch) -> None:
        monkeypatch.setattr("chalk_grader.sandbox.check_bwrap", lambda: "bwrap")
        args = bwrap_command("true", workdir=Path("/tmp/w"), network=True, env={})
        assert "--share-net" in args


@needs_bwrap
class TestSandbox:
    def test_result_and_workdir_are_writable(self, tmp_path) -> None:
        assert grade(tmp_path, report('echo x > out.txt && test "$(cat answer.txt)" = answer'))

    def test_home_only_shows_reexposed_paths(self, tmp_path) -> None:
        # PATH entries and chalk's Python may live under $HOME and are mounted
        # back; nothing else in $HOME is visible.
        graded = run(tmp_path, 'echo 1 > "$CHALK_RESULT"; ls -A "$HOME" >> "$CHALK_RESULT"\n')
        visible = set((graded.feedback or "").split())
        assert not visible & {".ssh", ".gnupg", ".config", ".bashrc", ".gitconfig"}

    def test_files_outside_workdir_are_hidden(self, tmp_path) -> None:
        secret = tmp_path / "secret.txt"
        secret.write_text("gabarito")
        assert grade(tmp_path, report(f"! test -e {secret}")) == 1

    def test_root_is_read_only(self, tmp_path) -> None:
        assert grade(tmp_path, report("! touch /etc/chalk-test 2>/dev/null")) == 1

    def test_network_is_off(self, tmp_path) -> None:
        check = (
            "! python3 -c 'import socket; socket.create_connection((\"1.1.1.1\", 53), 2)'"
            " 2>/dev/null"
        )
        assert grade(tmp_path, report(check)) == 1

    def test_mounts_expose_paths(self, tmp_path) -> None:
        data = tmp_path / "data"
        data.mkdir()
        (data / "x.txt").write_text("x")
        assert grade(tmp_path, report(f"test -e {data}/x.txt"), mounts=["data"]) == 1

    def test_mounts_expand_home(self, tmp_path, monkeypatch) -> None:
        home = tmp_path / "home"
        (home / ".tool").mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        check = report(f"test -d {home}/.tool")
        assert grade(tmp_path, check, mounts=["~/.tool"], pass_env=["HOME"]) == 1

    def test_timeout(self, tmp_path) -> None:
        start = time.time()
        assert grade(tmp_path, "sleep 10\n", timeout=0.3) == dq.Timeout()
        assert time.time() - start < 5
