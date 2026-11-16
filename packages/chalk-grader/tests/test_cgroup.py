"""
A cgroup for each run. These tests need a delegated cgroup, which pytest
gets when started as

    systemd-run --user --scope -p Delegate=yes .venv/bin/python -m pytest ...

(not under `uv run`: uv would share the scope). Elsewhere they are skipped,
except the ones that use a fake controller.
"""

import os
import shutil
import subprocess
import time
from fractions import Fraction
from pathlib import Path

import pytest
from conftest import FakeController
from test_data_profiles import make_grader
from test_script_limits import script_grader

from chalk_grader import cgroup
from chalk_grader import disqualification as dq
from chalk_grader.cgroup import Cgroup, Events
from chalk_grader.profiles import PrepareError, ReferenceMemoryLimit
from chalk_grader.script_runner import LAUNCHER, RunError, RunKilled, memory_feedback

needs_cgroup = pytest.mark.skipif(
    cgroup.controller() is None, reason="needs a delegated cgroup (see the docstring)"
)

#: Writes 400 MB, then reports a pass. (bytearray(n) alone would not do:
#: its pages are only reserved until written.)
GREEDY = """\
python3 -c 'b = bytearray(b"y") * 400_000_000'
echo 1 > "$CHALK_RESULT"
"""


MiB = 2**20


PASS = 'echo 1 > "$CHALK_RESULT"\n'

#: A JUnit report with one test that passes, for the profiles.
JUNIT = """echo '<testsuite><testcase classname="t" name="ok"/></testsuite>' > "$CHALK_RESULT\""""


class TestEvents:
    def test_over_memory(self) -> None:
        assert Events(oom=1, oom_kill=2, limit=MiB).over_memory
        assert not Events(oom=1, oom_kill=2, limit=MiB).killed_from_outside

    def test_killed_by_the_system(self) -> None:
        assert Events(oom_kill=1, limit=MiB).killed_from_outside
        assert not Events(oom_kill=1, limit=MiB).over_memory

    def test_without_a_limit_any_oom_kill_is_the_answer(self) -> None:
        events = Events(oom_kill=1)
        assert events.over_memory
        assert not events.killed_from_outside
        assert memory_feedback(events) == "The answer used too much memory."

    def test_killed_by_oomd(self) -> None:
        assert Events(oomd=1, limit=MiB).killed_from_outside
        assert not Events(oomd=1, limit=MiB).over_memory
        # Without a limit of its own, as for any OOM kill.
        assert Events(oomd=1).over_memory

    def test_quiet_run(self) -> None:
        assert not Events().over_memory
        assert not Events().killed_from_outside
        assert not Events(limit=MiB).over_memory


class TestBlame:
    """What a run gets from the events of its cgroup."""

    def test_killed_run_runs_again(self, tmp_path, fake_cgroups) -> None:
        fake = fake_cgroups(Events(oom_kill=1))
        graded = script_grader(tmp_path, PASS, limits={"memory": "100MiB"})("s1", "x")
        assert graded.score == 1
        assert fake.created == [(100 * MiB, 256), (100 * MiB, 256)]

    def test_killed_twice_is_not_graded(self, tmp_path, fake_cgroups) -> None:
        fake = fake_cgroups(Events(oom_kill=1), Events(oom_kill=1))
        grader = script_grader(tmp_path, PASS, limits={"memory": "100MiB"})
        with pytest.raises(RunKilled, match="twice"):
            grader("s1", "x")
        assert len(fake.created) == 2

    def test_oom_kill_without_a_limit_is_the_answer(self, tmp_path, fake_cgroups) -> None:
        fake = fake_cgroups(Events(oom_kill=1))
        graded = script_grader(tmp_path, PASS)("s1", "x")
        assert graded.score == dq.MemoryLimit()
        assert graded.feedback == "The answer used too much memory."
        assert fake.created == [(None, 256)]

    def test_over_its_own_limit(self, tmp_path, fake_cgroups) -> None:
        fake_cgroups(Events(oom=1, oom_kill=1))
        graded = script_grader(tmp_path, PASS, limits={"memory": "100MiB"})("s1", "x")
        assert graded.score == dq.MemoryLimit()
        assert graded.feedback == "The answer used more than 100 MiB of memory."


class TestLauncher:
    def test_failure_is_not_the_answer(self, tmp_path, monkeypatch) -> None:
        fake = FakeController(tmp_path / "cgroups")
        create = fake.create

        def broken(memory: int | None = None, processes: int | None = None) -> Cgroup:
            group = create(memory, processes)
            (group.path / "cgroup.procs").unlink()
            (group.path / "cgroup.procs").mkdir()
            return group

        monkeypatch.setattr(fake, "create", broken)
        monkeypatch.setattr(cgroup, "controller", lambda: fake)
        with pytest.raises(RunError, match="cannot join"):
            script_grader(tmp_path, PASS)("s1", "x")

    def test_exit_125_of_the_answer_is_its_own(self, tmp_path, fake_cgroups) -> None:
        fake_cgroups()
        assert script_grader(tmp_path, "exit 125\n")("s1", "x").score == dq.Error()

    def test_run_gets_no_other_descriptor(self, tmp_path, fake_cgroups) -> None:
        fake_cgroups()
        body = 'ls /proc/self/fd | wc -l > "$CHALK_RESULT"\n'
        # stdin, stdout, stderr and the directory ls reads.
        assert script_grader(tmp_path, body)("s1", "x").score == 4

    @pytest.mark.parametrize("shell", ["sh", "dash", "bash"])
    def test_any_posix_shell(self, tmp_path, shell) -> None:
        # /bin/sh is dash on Debian and Ubuntu, bash elsewhere.
        path = shutil.which(shell)
        if path is None:
            pytest.skip(f"no {shell}")
        report = tmp_path / "failure"
        args = ["chalk-run", "", "1048576", "1024", str(report), "echo", "ok"]
        proc = subprocess.run([path, "-c", LAUNCHER, *args], capture_output=True, text=True)
        assert (proc.returncode, proc.stdout) == (0, "ok\n")
        assert not report.exists() or not report.read_text()

    def test_sizes_round_up(self, tmp_path, no_cgroups) -> None:
        body = '[ "$(ulimit -f)" = 1 ] && echo 1 > "$CHALK_RESULT" || echo 0 > "$CHALK_RESULT"\n'
        assert script_grader(tmp_path, body, limits={"file_size": "100B"})("s1", "x").score == 1


class TestAddressSpace:
    CHECK = '[ "$(ulimit -v)" = {} ] && echo 1 > "$CHALK_RESULT" || echo 0 > "$CHALK_RESULT"\n'

    def test_memory_is_the_address_space_without_cgroups(self, tmp_path, no_cgroups) -> None:
        body = self.CHECK.format(200 * 1024)
        graded = script_grader(tmp_path, body, limits={"memory": "200MiB"})("s1", "x")
        assert graded.score == 1

    def test_memory_is_not_the_address_space_with_cgroups(self, tmp_path, fake_cgroups) -> None:
        fake_cgroups()
        body = self.CHECK.format("unlimited")
        graded = script_grader(tmp_path, body, limits={"memory": "200MiB"})("s1", "x")
        assert graded.score == 1

    def test_address_space_wins(self, tmp_path, no_cgroups) -> None:
        body = self.CHECK.format(300 * 1024)
        limits = {"memory": "200MiB", "address_space": "300MiB"}
        assert script_grader(tmp_path, body, limits=limits)("s1", "x").score == 1


@pytest.mark.skipif(not shutil.which("systemctl"), reason="needs systemctl")
def test_no_reexec_without_the_systemd_of_the_user(monkeypatch) -> None:
    def execv(*args: object) -> None:
        raise AssertionError("must not run systemd-run")

    monkeypatch.delenv(cgroup.REEXEC_ENV, raising=False)
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/nonexistent")
    monkeypatch.setattr(cgroup, "current", lambda: Path("/sys/fs/cgroup/session-1.scope"))
    monkeypatch.setattr(cgroup, "_delegated", lambda path: False)
    monkeypatch.setattr(cgroup.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cgroup.os, "execv", execv)
    cgroup.reexec_delegated(["true"])
    assert cgroup.REEXEC_ENV not in os.environ


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
        graded = script_grader(tmp_path, GREEDY, limits={"memory": "50MiB"})("s1", "x")
        assert graded.score == dq.MemoryLimit()
        own = cgroup.current()
        assert own is not None and own.name == cgroup.SUPERVISOR
        assert os.getpid() in map(int, (own / "cgroup.procs").read_text().split())
        # The next run works, in a cgroup of its own.
        assert script_grader(tmp_path, PASS)("s2", "x").score == 1
        assert not list(own.parent.glob("run-*"))

    def test_memory_max_of_the_run(self, tmp_path) -> None:
        body = 'cat "/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)/memory.max" > "$CHALK_RESULT"\n'
        graded = script_grader(tmp_path, body, limits={"memory": "100MiB"})("s1", "x")
        assert graded.score == 100 * MiB

    def test_memory_is_not_the_address_space(self, tmp_path) -> None:
        body = TestAddressSpace.CHECK.format("unlimited")
        assert script_grader(tmp_path, body, limits={"memory": "1GiB"})("s1", "x").score == 1

    def test_supervisor_avoids_oomd(self) -> None:
        own = cgroup.current()
        assert own is not None
        assert os.getxattr(own, "user.oomd_avoid") == b"1"

    def test_oomd_kill_is_read(self) -> None:
        found = cgroup.controller()
        assert found is not None
        run = found.create(memory=MiB, processes=None)
        try:
            # As systemd-oomd marks what it kills.
            os.setxattr(run.path, "user.oomd_ooms", b"1")
            assert run.events().oomd == 1
            assert run.events().killed_from_outside
        finally:
            run.close()

    def test_kill_all(self, tmp_path) -> None:
        found = cgroup.controller()
        assert found is not None
        run = found.create(memory=None, processes=None)
        assert run.path.is_dir()
        found.kill_all()
        assert not run.path.exists()


@needs_cgroup
def test_reference_over_its_memory(tmp_path) -> None:
    template = tmp_path / "q" / "template"
    template.mkdir(parents=True)
    solution = tmp_path / "solution"
    solution.mkdir()
    profile = {"test": {"command": GREEDY}, "vars": {"memory_mib": "100"}}
    grader = make_grader(template, solution, {"shell-tests": profile}, sandbox="none")
    with pytest.raises(ReferenceMemoryLimit, match="more than 100 MiB"):
        grader.prepare()


@needs_cgroup
class TestPrepareCgroup:
    """The prepare commands run in cgroups of their own."""

    def grader(self, tmp_path, command: str, timeout: float | None = None):
        template = tmp_path / "q" / "template"
        template.mkdir(parents=True)
        solution = tmp_path / "solution"
        solution.mkdir()
        profile = {
            "prepare": {"commands": [command], "timeout": timeout},
            "test": {"command": JUNIT},
        }
        return make_grader(template, solution, {"shell-tests": profile}, sandbox="none")

    def wait_gone(self, pid: int) -> bool:
        deadline = time.monotonic() + 5
        while Path(f"/proc/{pid}").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        return not Path(f"/proc/{pid}").exists()

    def test_in_a_run_cgroup(self, tmp_path) -> None:
        out = tmp_path / "cgroup"
        self.grader(tmp_path, f"cat /proc/self/cgroup > {out}").prepare()
        assert "/run-" in out.read_text()

    def test_leaves_nothing_behind(self, tmp_path) -> None:
        pidfile = tmp_path / "pid"
        command = f"setsid sleep 60 > /dev/null 2>&1 & echo $! > {pidfile}"
        self.grader(tmp_path, command).prepare()
        assert self.wait_gone(int(pidfile.read_text()))
        own = cgroup.current()
        assert own is not None and not list(own.parent.glob("run-*"))

    def test_timeout_kills_the_tree(self, tmp_path) -> None:
        pidfile = tmp_path / "pid"
        command = f"setsid sleep 60 > /dev/null 2>&1 & echo $! > {pidfile}; sleep 60"
        start = time.monotonic()
        with pytest.raises(PrepareError, match="timed out"):
            self.grader(tmp_path, command, timeout=1).prepare()
        assert time.monotonic() - start < 10
        assert self.wait_gone(int(pidfile.read_text()))
