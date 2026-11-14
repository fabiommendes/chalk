"""
A fake cgroup controller, for the tests of what a run does with the
events of its cgroup without a delegated cgroup.
"""

import shutil
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from chalk_grader import cgroup
from chalk_grader.cgroup import Cgroup, Events


@dataclass(frozen=True)
class FakeCgroup(Cgroup):
    """A directory in place of a cgroup, with the events given."""

    given: Events = Events()

    def events(self) -> Events:
        return replace(self.given, limit=self.memory)

    def close(self, wait: float = 5.0) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


class FakeController:
    """
    Records the cgroups the runs ask for. The events of each run come from
    `events`, in order; then runs are quiet.
    """

    def __init__(self, root: Path, events: list[Events] | None = None) -> None:
        self.root = root
        self.events = events or []
        #: (memory, processes) of each run.
        self.created: list[tuple[int | None, int | None]] = []

    def create(self, memory: int | None = None, processes: int | None = None) -> Cgroup:
        path = self.root / f"run-{len(self.created)}"
        path.mkdir(parents=True)
        (path / "cgroup.procs").write_text("")
        self.created.append((memory, processes))
        given = self.events.pop(0) if self.events else Events()
        return FakeCgroup(path, memory, processes, given)


@pytest.fixture
def fake_cgroups(monkeypatch, tmp_path):
    """Install a FakeController made from the given events."""

    def install(*events: Events) -> FakeController:
        fake = FakeController(tmp_path / "cgroups", list(events))
        monkeypatch.setattr(cgroup, "controller", lambda: fake)
        return fake

    return install


@pytest.fixture
def no_cgroups(monkeypatch) -> None:
    monkeypatch.setattr(cgroup, "controller", lambda: None)
