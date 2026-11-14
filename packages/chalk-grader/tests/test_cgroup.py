"""
A cgroup for each run. These tests need a delegated cgroup, which pytest
gets when started as

    systemd-run --user --scope -p Delegate=yes .venv/bin/python -m pytest ...

(not under `uv run`: uv would share the scope). Elsewhere they are skipped,
except the ones about the events.
"""

import os
import time
from fractions import Fraction
from pathlib import Path

import pytest
from test_script_limits import script_grader

from chalk_grader import cgroup
from chalk_grader import disqualification as dq
from chalk_grader.cgroup import Events

needs_cgroup = pytest.mark.skipif(
    cgroup.controller() is None, reason="needs a delegated cgroup (see the docstring)"
)

#: Writes 400 MB, then reports a pass. (bytearray(n) alone would not do:
#: its pages are only reserved until written.)
GREEDY = """\
python3 -c 'b = bytearray(b"y") * 400_000_000'
echo 1 > "$CHALK_RESULT"
"""


class TestEvents:
    def test_over_memory(self) -> None:
        assert Events(oom=1, oom_kill=2).over_memory
        assert not Events(oom=1, oom_kill=2).killed_from_outside

    def test_killed_by_the_system(self) -> None:
        assert Events(oom_kill=1).killed_from_outside
        assert not Events(oom_kill=1).over_memory

    def test_quiet_run(self) -> None:
        assert not Events().over_memory
        assert not Events().killed_from_outside


@needs_cgroup
class TestRunCgroup:
    def test_grader_is_in_the_supervisor(self) -> None:
        own = cgroup.current()
        assert own is not None and own.name == cgroup.SUPERVISOR

    def test_memory_limit(self, tmp_path) -> None:
        graded = script_grader(tmp_path, GREEDY, limits={"memory": "100MiB"})("s1", "x")
        assert graded.score == dq.MemoryLimit()
        assert graded.feedback == "The answer used more than 100 MiB of memory."

    def test_within_the_limit(self, tmp_path) -> None:
        graded = script_grader(tmp_path, GREEDY, limits={"memory": "1GiB"})("s1", "x")
        assert graded.score == 1

    def test_fork_bomb_stops_at_the_process_limit(self, tmp_path) -> None:
        bomb = (
            "import os, time\n"
            "n = 0\n"
            "try:\n"
            "    for _ in range(100):\n"
            "        if os.fork() == 0:\n"
            "            time.sleep(5)\n"
            "            os._exit(0)\n"
            "        n += 1\n"
            "except OSError:\n"
            "    pass\n"
            "print(n)\n"
        )
        (tmp_path / "bomb.py").write_text(bomb)
        body = f'n=$(python3 {tmp_path}/bomb.py)\necho "$n/100" > "$CHALK_RESULT"\n'
        graded = script_grader(tmp_path, body, limits={"processes": 20})("s1", "x")
        assert 0 < graded.score < Fraction(20, 100)

    def test_processes_that_leave_the_group_are_killed(self, tmp_path) -> None:
        pidfile = tmp_path / "pid"
        body = f'setsid sleep 60 & echo $! > {pidfile}\necho 1 > "$CHALK_RESULT"\n'
        assert script_grader(tmp_path, body)("s1", "x").score == 1
        pid = int(pidfile.read_text())
        deadline = time.monotonic() + 5
        while Path(f"/proc/{pid}").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not Path(f"/proc/{pid}").exists()

    def test_runs_leave_no_cgroup(self, tmp_path) -> None:
        own = cgroup.current()
        assert own is not None
        script_grader(tmp_path, 'echo 1 > "$CHALK_RESULT"\n')("s1", "x")
        assert not list(own.parent.glob("run-*"))

    def test_grader_survives(self, tmp_path) -> None:
        script_grader(tmp_path, GREEDY, limits={"memory": "50MiB"})("s1", "x")
        assert os.getpid() in map(int, (cgroup.current() / "cgroup.procs").read_text().split())  # type: ignore[operator]
