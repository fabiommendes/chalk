"""
Services of a profile: programs the student's code talks to through the
network, such as an HTTP server.

Each service runs in its own bwrap sandbox, with its own loopback, in a copy
of the template. The student's sandbox reaches it through a Unix socket
(see runners/net.py). The directory with the services' files is hidden from
the student's sandbox, except the sockets, so the student's code cannot read
or change the service's files or its report, nor signal its processes.

The services start before the test step of each run, so every student finds
them in the same state, and stop after it. A service may write a JUnit
report to $CHALK_RESULT when it gets SIGTERM, with tests about what it
received; those tests count in the grade.
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping
from logging import getLogger
from pathlib import Path

from ..core import models
from .repo import Repo
from .result_extractor import MAX_RESULT_SIZE
from .sandbox import bwrap_command
from .script_runner import PASS_ENV

__all__ = ["Services"]

log = getLogger(__name__)

#: Files chalk ships for the profiles: the stdio runner, net.py and chalk_test.h.
RUNNERS = Path(__file__).parent / "runners"

#: Seconds a service has to exit after SIGTERM, before SIGKILL.
GRACE = 5.0

#: Lines of the service output shown when it does not start.
LOG_TAIL = 20


class Services:
    """
    The services of one run.
    """

    def __init__(
        self,
        specs: Mapping[str, models.Service],
        *,
        template: Path,
        render: Callable[[str, Mapping[str, str]], str],
        readable: Iterable[Path] = (),
        env: Mapping[str, str] | None = None,
    ) -> None:
        """
        Args:
            specs: the services by name.
            template: directory copied to the working directory of each one.
            render: function that replaces the variables in a text, given
                the extra variables of the service.
            readable: paths the services' sandboxes mount read only.
            env: CHALK_* variables of the run, such as CHALK_STUDENT.
        """
        self.specs = dict(specs)
        self.template = template
        self._render = render
        self._readable = [RUNNERS, *readable]
        self._env = dict(env or {})
        self.root = Path(tempfile.mkdtemp(prefix="chalk-services-"))
        self.sockets = self.root / "sockets"
        self.sockets.mkdir()
        self._procs: dict[str, subprocess.Popen[bytes]] = {}
        self._reports: list[str] | None = None

    def start(self) -> str | None:
        """
        Start every service and wait until they accept connections. Return
        None, or the reason a service did not start.
        """
        for name, spec in self.specs.items():
            self._procs[name] = self._spawn(name, spec)

        for name, spec in self.specs.items():
            proc = self._procs[name]
            deadline = time.monotonic() + spec.start_timeout
            while not self.socket(name).exists():
                if proc.poll() is not None:
                    return self._failure(name, f"exited with code {proc.returncode}")
                if time.monotonic() > deadline:
                    return self._failure(
                        name, f"did not open port {spec.port} in {spec.start_timeout:g}s"
                    )
                time.sleep(0.02)
        return None

    def socket(self, name: str) -> Path:
        return self.sockets / name

    def forward(self, command: str) -> str:
        """
        Wrap the shell command of the test step, so the ports of the services
        are open while it runs.
        """
        maps = [f"--map={s.port}={self.socket(n)}" for n, s in self.specs.items()]
        args = [sys.executable, "-I", str(RUNNERS / "net.py"), "forward", *maps]
        return f"{shlex.join(args)} -- /bin/sh -c {shlex.quote(command)}"

    def stop(self, repo: Repo | None = None) -> list[str]:
        """
        Stop the services and return their reports. The output of each
        service goes to the file chalk.service.<name> of the repository.

        Only the first call stops them; the others return the same reports.
        """
        if self._reports is not None:
            return self._reports

        for proc in self._procs.values():
            if proc.stdin is not None:
                proc.stdin.close()
        reports: list[str] = []
        for name, proc in self._procs.items():
            try:
                proc.wait(GRACE + 5)
            except subprocess.TimeoutExpired:
                log.warning(f"Service {name} did not stop; killing it")
                _kill(proc)
                proc.wait()
            report = self.root / name / "out" / "result"
            if report.is_file() and report.stat().st_size <= MAX_RESULT_SIZE:
                reports.append(report.read_text(errors="replace"))
            if repo is not None and (output := self._log(name)).exists():
                shutil.copyfile(output, repo.root / f"chalk.service.{name}")
        shutil.rmtree(self.root, ignore_errors=True)
        self._reports = reports
        return reports

    def __del__(self) -> None:
        for proc in getattr(self, "_procs", {}).values():
            _kill(proc)
        shutil.rmtree(getattr(self, "root", ""), ignore_errors=True)

    def _spawn(self, name: str, spec: models.Service) -> subprocess.Popen[bytes]:
        base = self.root / name
        work, out = base / "work", base / "out"
        shutil.copytree(self.template, work, symlinks=True)
        out.mkdir()

        variables = {"workdir": str(work)}
        env = {k: os.environ[k] for k in PASS_ENV if k in os.environ}
        env.update(self._env)
        env["CHALK_RESULT"] = str(out / "result")
        env.update({k: self._render(v, variables) for k, v in spec.env.items()})

        command = self._render(spec.command, variables)
        serve = [
            sys.executable,
            "-I",
            str(RUNNERS / "net.py"),
            "serve",
            f"--socket={self.socket(name)}",
            f"--port={spec.port}",
            f"--grace={GRACE}",
            "--",
            command,
        ]
        args = bwrap_command(
            shlex.join(serve),
            workdir=work,
            writable=[out, self.sockets],
            readable=self._readable,
            env=env,
        )
        with self._log(name).open("wb") as output:
            return subprocess.Popen(
                args,
                cwd=work,
                env=env,
                stdin=subprocess.PIPE,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

    def _log(self, name: str) -> Path:
        return self.root / name / "output"

    def _failure(self, name: str, reason: str) -> str:
        output = self._log(name).read_text(errors="replace") if self._log(name).exists() else ""
        tail = "\n".join(output.splitlines()[-LOG_TAIL:])
        message = f"The service {name} {reason}."
        log.warning(f"{message}\n{tail}".rstrip())
        return f"{message}\n{tail}".rstrip()


def _kill(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
