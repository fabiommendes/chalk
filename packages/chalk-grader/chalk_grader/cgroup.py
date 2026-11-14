"""
A cgroup v2 for each run, so that a run that takes too much memory or
starts too many processes is stopped on its own, without touching the
grader or the other runs.

The grader must live in a cgroup delegated to it: a systemd unit with
`Delegate=yes`, as `systemd-run --user --scope -p Delegate=yes` makes (see
`reexec_delegated`). On the first run, the grader moves itself to a
`supervisor` child and enables the memory and pids controllers; each run
then gets a `run-*` child of its own:

    <delegated cgroup>/
        supervisor/     the grader, with its threads
        run-<id>/       one run: memory.max, memory.swap.max=0, pids.max,
                        memory.oom.group=1

The process of the run joins its cgroup before it executes anything (see
`LAUNCHER` in script_runner.py). Without a delegated cgroup, `controller()`
returns None and runs have no memory or process limit besides those of
their runtime.

The grader should call `controller()` before it starts any process of its
own (such as the services of a profile): the setup gives up when the
delegated cgroup has other processes.
"""

from __future__ import annotations

import atexit
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path

__all__ = [
    "REEXEC_ENV",
    "Cgroup",
    "CgroupController",
    "Events",
    "controller",
    "reexec_delegated",
]

log = getLogger(__name__)

ROOT = Path("/sys/fs/cgroup")
SUPERVISOR = "supervisor"
CONTROLLERS = ("memory", "pids")

#: Set when the grader runs again under systemd-run, so it does not loop.
REEXEC_ENV = "CHALK_CGROUP_REEXEC"


@dataclass(frozen=True)
class Events:
    """
    What happened in a run, from the event files of its cgroup.
    """

    #: Times the memory of the run reached memory.max and the kernel found
    #: nothing to reclaim.
    oom: int = 0
    #: Processes of the run killed by any OOM killer, the system's included.
    oom_kill: int = 0
    #: Times a fork failed because of pids.max.
    pids_max: int = 0
    #: Largest memory of the run, in bytes, if the kernel reports it.
    peak: int | None = None
    #: memory.max of the run, in bytes, or None when the run has none.
    limit: int | None = None

    @property
    def over_memory(self) -> bool:
        """
        The run took too much memory and was killed for it: it went past its
        own limit, or, without a limit of its own, the system's OOM killer
        chose it. Without a limit, every OOM is global, and the answer that
        takes the memory of the machine is the likeliest choice.
        """
        if self.limit is None:
            return self.oom_kill > 0
        return self.oom > 0 and self.oom_kill > 0

    @property
    def killed_from_outside(self) -> bool:
        """
        A process of the run was killed by the system's OOM killer, while the
        run was within its own memory limit.
        """
        return self.limit is not None and self.oom_kill > 0 and self.oom == 0


@dataclass(frozen=True)
class Cgroup:
    """
    The cgroup of one run. `close()` kills what is left in it and removes it.
    """

    path: Path
    memory: int | None
    processes: int | None

    def events(self) -> Events:
        memory = _keyed(self.path / "memory.events")
        pids = _keyed(self.path / "pids.events")
        peak = _read(self.path / "memory.peak")
        return Events(
            oom=memory.get("oom", 0),
            oom_kill=memory.get("oom_kill", 0),
            pids_max=pids.get("max", 0),
            peak=int(peak) if peak and peak.isdigit() else None,
            limit=self.memory,
        )

    def kill(self) -> None:
        """
        Kill every process of the run, including those that left its process
        group.
        """
        try:
            (self.path / "cgroup.kill").write_text("1")
        except OSError:
            pass

    def close(self, wait: float = 5.0) -> None:
        self.kill()
        deadline = time.monotonic() + wait
        while True:
            try:
                self.path.rmdir()
                return
            except FileNotFoundError:
                return
            except OSError:
                # EBUSY until the killed processes are gone.
                if time.monotonic() > deadline:
                    log.warning(f"cannot remove the cgroup {self.path}")
                    return
                time.sleep(0.01)


class CgroupController:
    """
    Creates the cgroups of the runs under a delegated cgroup.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def create(self, memory: int | None = None, processes: int | None = None) -> Cgroup:
        path = self.root / f"run-{uuid.uuid4().hex[:12]}"
        path.mkdir()
        try:
            if memory is not None:
                (path / "memory.max").write_text(str(memory))
                # Without swap, the run is killed instead of the machine
                # swapping. The file is missing when swap accounting is off.
                swap = path / "memory.swap.max"
                if swap.exists():
                    swap.write_text("0")
            # Kill the whole run, not one of its processes.
            (path / "memory.oom.group").write_text("1")
            if processes is not None:
                (path / "pids.max").write_text(str(processes))
        except OSError:
            path.rmdir()
            raise
        return Cgroup(path, memory, processes)

    def kill_all(self) -> None:
        """
        Kill the runs that are left, such as those of a grader stopped by a
        signal, so that they do not keep its systemd scope alive.
        """
        for path in self.root.glob("run-*"):
            Cgroup(path, None, None).close(wait=1.0)


_lock = threading.Lock()
_controller: list[CgroupController | None] = []


def controller() -> CgroupController | None:
    """
    The controller of the cgroups of the runs, or None when the grader is
    not in a delegated cgroup. The first call moves the grader to the
    `supervisor` child of its cgroup; a warning says why there is none.
    """
    with _lock:
        if not _controller:
            try:
                found = _setup()
            except _NotDelegated as e:
                log.warning(f"runs have no memory or process limit: {e}")
                _controller.append(None)
            else:
                _controller.append(found)
                _clean_up_on_exit(found)
        return _controller[0]


#: Signals after which the grader kills its runs before it dies.
_SIGNALS = (signal.SIGTERM, signal.SIGHUP)


def _clean_up_on_exit(found: CgroupController) -> None:
    """
    Kill the runs that are left when the grader exits, or when it gets a
    signal that would end it without running atexit. Ctrl-C raises
    KeyboardInterrupt, which ends in atexit. SIGKILL cannot be caught: its
    runs end with their scope or with their own timeout.
    """
    atexit.register(found.kill_all)
    if threading.current_thread() is not threading.main_thread():
        return

    def handler(signum: int, frame: object) -> None:
        found.kill_all()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for signum in _SIGNALS:
        if signal.getsignal(signum) == signal.SIG_DFL:
            signal.signal(signum, handler)


class _NotDelegated(Exception):
    pass


def _setup() -> CgroupController:
    if sys.platform != "linux":
        raise _NotDelegated("cgroups need Linux")
    own = current()
    if own is None:
        raise _NotDelegated("cgroup v2 is not mounted at /sys/fs/cgroup")
    if own.name == SUPERVISOR and _is_ours(own.parent):
        # Set up already, maybe in part, by an earlier controller of this
        # process.
        _enable_controllers(own.parent)
        return CgroupController(own.parent)
    if not _is_ours(own):
        raise _NotDelegated(
            f"the cgroup {own} is not delegated to this process; run it under "
            "`systemd-run --user --scope -p Delegate=yes`"
        )
    available = (_read(own / "cgroup.controllers") or "").split()
    missing = [c for c in CONTROLLERS if c not in available]
    if missing:
        raise _NotDelegated(f"the cgroup {own} lacks the {' and '.join(missing)} controllers")
    others = [p for p in _pids(own) if p != os.getpid()]
    if others:
        raise _NotDelegated(
            f"the cgroup {own} has other processes ({', '.join(map(str, others[:5]))})"
        )

    supervisor = own / SUPERVISOR
    supervisor.mkdir(exist_ok=True)
    try:
        (supervisor / "cgroup.procs").write_text(str(os.getpid()))
    except OSError as e:
        raise _NotDelegated(f"cannot set up the cgroup {own}: {e.strerror}") from e
    try:
        _enable_controllers(own)
    except _NotDelegated:
        # Such as a process that joined the cgroup after the check above.
        # Back to where the grader was, so that a later call sees the same
        # state as this one.
        try:
            (own / "cgroup.procs").write_text(str(os.getpid()))
            supervisor.rmdir()
        except OSError:
            pass
        raise
    return CgroupController(own)


def _enable_controllers(path: Path) -> None:
    control = path / "cgroup.subtree_control"
    if set(CONTROLLERS) <= set((_read(control) or "").split()):
        return
    try:
        control.write_text(" ".join(f"+{c}" for c in CONTROLLERS))
    except OSError as e:
        raise _NotDelegated(f"cannot enable the controllers of {path}: {e.strerror}") from e


def current() -> Path | None:
    """The cgroup v2 of this process, or None without cgroup v2."""
    try:
        lines = Path("/proc/self/cgroup").read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("0::"):
            path = ROOT / line.removeprefix("0::").lstrip("/")
            return path if (path / "cgroup.procs").exists() else None
    return None


def reexec_delegated(argv: list[str] | None = None) -> None:
    """
    Run this program again inside a delegated cgroup, a scope of the user's
    systemd, when it is not in one already. Returns when that cannot be
    done: no systemd-run, no systemd of the user to talk to (ssh without
    lingering, cron, a container), cgroup v1, or this is the run again.
    """
    if os.environ.get(REEXEC_ENV) or sys.platform != "linux":
        return
    own = current()
    systemd_run = shutil.which("systemd-run")
    if own is None or systemd_run is None or _delegated(own):
        return
    if not _user_manager():
        log.warning(
            "runs have no memory or process limit: the systemd of the user does not "
            "answer, so chalk cannot run in a delegated cgroup"
        )
        return
    argv = argv if argv is not None else [sys.executable, *sys.orig_argv[1:]]
    os.environ[REEXEC_ENV] = "1"
    command = [systemd_run, "--user", "--scope", "--quiet", "--collect", "-p", "Delegate=yes"]
    try:
        os.execv(systemd_run, [*command, "--", *argv])
    except OSError as e:
        log.warning(f"cannot run under systemd-run: {e.strerror}")


def _user_manager() -> bool:
    """The systemd of the user answers on its bus, as systemd-run needs."""
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _delegated(path: Path) -> bool:
    """
    The cgroup is a systemd unit with Delegate=yes, or the supervisor of
    one this process set up.
    """
    if path.name == SUPERVISOR:
        return _is_ours(path.parent)
    if not path.name.endswith((".scope", ".service")):
        return False
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "show", "--property=Delegate", "--value", path.name],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.stdout.strip() == "yes"


def _is_ours(path: Path) -> bool:
    """A cgroup this process may manage: it can change its controllers."""
    control = path / "cgroup.subtree_control"
    try:
        return control.stat().st_uid == os.getuid() and os.access(control, os.W_OK)
    except OSError:
        return False


def _pids(path: Path) -> list[int]:
    return [int(p) for p in (_read(path / "cgroup.procs") or "").split()]


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _keyed(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in (_read(path) or "").splitlines():
        key, _, value = line.partition(" ")
        if value.isdigit():
            out[key] = int(value)
    return out
