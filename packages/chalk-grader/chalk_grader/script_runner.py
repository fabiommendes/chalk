from __future__ import annotations

import os
import pty
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Any

from . import cgroup, models
from . import disqualification as dq
from .cgroup import Cgroup, Events
from .disqualification import Disqualified
from .graded import CaseResult, Graded
from .repo import Repo
from .result_extractor import extract_result_from_file
from .sandbox import bwrap_command
from .score import Score

__all__ = [
    "DEFAULT_PROCESSES",
    "LAUNCHER",
    "ChalkEnv",
    "Result",
    "RunKilled",
    "ScriptRunner",
]
log = getLogger(__name__)

#: Variables passed from chalk's environment to the autograder script. The
#: rest (tokens, SSH agent, cloud credentials...) is dropped. Questions can
#: add more with `autograder.pass_env`.
PASS_ENV = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMPDIR",
    "TZ",
    "LD_LIBRARY_PATH",
    "PYTHONPATH",
    "PYTHONHOME",
)
#: Most processes and threads a run may have at once, when the limits do
#: not say (pids.max of its cgroup).
DEFAULT_PROCESSES = 256

#: Shell script that starts every run: it joins the cgroup of the run ($1),
#: applies the address space ($2, KiB) and file size ($3, 512-byte blocks)
#: limits and executes the rest of its arguments. It replaces preexec_fn,
#: which may deadlock the child of a process with threads.
LAUNCHER = """\
if [ -n "$1" ]; then echo $$ > "$1/cgroup.procs" || exit 125; fi
if [ -n "$2" ]; then ulimit -v "$2" || exit 125; fi
if [ -n "$3" ]; then ulimit -f "$3" || exit 125; fi
shift 3
exec "$@"
"""

ANSI_REGEX = re.compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")


@dataclass
class Result:
    return_code: int
    #: None when the answer goes to manual grading.
    score: Score | Disqualified | None
    feedback: str | None = None
    stdout: str | None = None
    #: Notes for the teacher, never shown to the student.
    notes: str | None = None
    #: Outcome of each expected test, when the result came from a test report.
    cases: tuple[CaseResult, ...] | None = None

    def __bool__(self) -> bool:
        return self.return_code == 0


class RunKilled(RuntimeError):
    """
    The system killed a process of the run, for a reason that is not the
    answer's fault, such as the memory of the machine running out. The run
    may pass on another try.
    """


class ScriptRunner:
    """
    Run an autograder script in a subprocess and extract the feedback and the
    grade from the generated report file.
    """

    def __init__(
        self,
        script_path: Path | None,
        repo: Repo,
        /,
        *,
        env: ChalkEnv,
        command: str | None = None,
        extra_env: dict[str, str | None] | None = None,
        result_reader: Callable[[Path], Graded | None] | None = None,
        timeout: float,
        on_output_line: Callable[[str], Any] | None = None,
        capture_output: bool = True,
        limits: models.Limits | None = None,
        sandbox: Sandbox | None = None,
        log_name: str = "chalk.stdout",
        expect_result: bool = True,
    ) -> None:
        self._chalk_env = env
        self._log_name = log_name
        #: False for steps that only report by the exit code, such as a build.
        self._expect_result = expect_result
        self.timeout = timeout
        self.script_path = script_path
        self._repo = repo
        self._on_output_line = on_output_line or (lambda _: None)
        self._result: Result | None = None
        self._result_reader = result_reader or extract_result_from_file

        if command is None:
            if script_path is None:
                raise ValueError("either a script or a command is required")
            elif not script_path.exists():
                raise OSError(f"Script not found: {script_path}")
            elif not script_path.is_file():
                raise OSError(f"Script is not a file: {script_path}")
            command = self._get_shell_command(script_path)

        self._master_pty_fd, self._slave_pty_fd = pty.openpty()
        self.capture_output = capture_output

        # The result file lives outside the working directory, where the
        # student's code cannot reach it once the run is sandboxed.
        self._result_dir = Path(tempfile.mkdtemp(prefix="chalk-result-"))
        self.result_path = self._result_dir / "result"

        env = self._chalk_env.to_env_dict(repo.root, self.result_path)
        for key, value in (extra_env or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value

        args = ["/bin/sh", "-c", command]
        if sandbox is not None:
            readable = (
                [*sandbox.readable] if script_path is None else [script_path, *sandbox.readable]
            )
            args = bwrap_command(
                command,
                workdir=repo.root,
                writable=[self._result_dir],
                readable=readable,
                overlays=sandbox.overlays,
                network=sandbox.network,
                env=env,
                hidden=sandbox.hidden,
            )

        self._cgroup: Cgroup | None = None
        if (cgroups := cgroup.controller()) is not None:
            limits = limits or models.Limits()
            memory = None if limits.memory is None else int(limits.memory)
            processes = DEFAULT_PROCESSES if limits.processes is None else limits.processes
            self._cgroup = cgroups.create(memory=memory, processes=processes)
        try:
            self.process = self._start(args, limits, repo.root, env, capture_output)
        except BaseException:
            self._close_cgroup()
            raise

    def _start(
        self,
        args: list[str],
        limits: models.Limits | None,
        cwd: Path,
        env: dict[str, str],
        capture_output: bool,
    ) -> subprocess.Popen[bytes]:
        address_space = limits and limits.address_space
        file_size = limits and limits.file_size
        launcher = [
            "/bin/sh",
            "-c",
            LAUNCHER,
            "chalk-run",
            str(self._cgroup.path) if self._cgroup else "",
            str(int(address_space) // 1024) if address_space else "",
            str(int(file_size) // 512) if file_size else "",
        ]
        return subprocess.Popen(
            [*launcher, *args],
            cwd=cwd,
            env=env,
            stdout=self._slave_pty_fd if capture_output else None,
            stderr=self._slave_pty_fd if capture_output else None,
            stdin=subprocess.DEVNULL,
            # Own process group, so a timeout kills the whole tree and not
            # only the shell.
            start_new_session=True,
        )

    def __del__(self) -> None:
        self._kill_group()
        self._close_cgroup()
        shutil.rmtree(getattr(self, "_result_dir", ""), ignore_errors=True)

    def _close_cgroup(self) -> Events | None:
        """
        Kill what is left of the run, remove its cgroup and return what
        happened in it.
        """
        group = getattr(self, "_cgroup", None)
        if group is None:
            return None
        self._cgroup = None
        events = group.events()
        group.close()
        return events

    def _kill_group(self) -> None:
        """
        Kill the script and every process it started that is still alive,
        including background processes left behind after a normal exit.
        """
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, AttributeError):
            pass

    def run(self) -> Result:
        if self._result is not None:
            return self._result

        if self.capture_output:
            timeout, stdout = self._run_to_stdout()
        else:
            timeout = self._run_no_capture()
            stdout = ""
        self._kill_group()
        events = self._close_cgroup()
        self._repo.write_file(self._log_name, stdout)
        student = self._chalk_env.student_id
        if events is not None and events.pids_max:
            log.info(f"The run of {student} reached its process limit {events.pids_max} times")
        if events is not None and events.over_memory:
            shutil.rmtree(self._result_dir, ignore_errors=True)
            return Result(
                return_code=self.process.returncode,
                score=dq.MemoryLimit(),
                feedback=memory_feedback(events),
                stdout=stdout,
            )
        if events is not None and events.killed_from_outside:
            shutil.rmtree(self._result_dir, ignore_errors=True)
            raise RunKilled(f"the system killed a process of the run of {student}")

        # The script may hang (timeout=True), and even so it may generate a valid report file.
        # We test this here and only create a timeout score if the report file is not generated.
        result = self.read_result()
        if self.result_path.exists():
            shutil.copyfile(self.result_path, self._repo.root / "chalk.result")
        shutil.rmtree(self._result_dir, ignore_errors=True)

        if result is None:
            if self._expect_result:
                log.warning(
                    f"Process terminated without generating report file for student {student}"
                )

            if timeout:
                return Result(-1, score=dq.Timeout(), stdout=stdout)

            return Result(
                return_code=self.process.returncode,
                score=dq.Error(),
                feedback="The autograder script failed to generate a report file.",
                stdout=stdout,
            )

        return Result(
            return_code=self.process.returncode,
            stdout=stdout,
            feedback=result.feedback,
            score=result.score,
            cases=result.cases,
        )

    def _run_to_stdout(self) -> tuple[bool, str]:
        deadline = (self.timeout or float("inf")) + time.time()
        process = self.process
        fd = self._master_pty_fd

        timeout = False
        dt = 0.025
        output_lines: list[str] = []
        buf = b""
        os.set_blocking(fd, False)

        def emit(line: bytes) -> None:
            text = line.removesuffix(b"\r").decode(errors="replace")
            self._on_output_line(text)
            output_lines.append(text)

        def feed(chunk: bytes) -> None:
            nonlocal buf
            *lines, buf = (buf + chunk).split(b"\n")
            for line in lines:
                emit(line)

        def read() -> bytes | None:
            """Available output, b"" at the end, None if nothing yet."""
            try:
                return os.read(fd, 65536)
            except BlockingIOError:
                return None
            except OSError:
                # EIO: every process holding the pty slave has exited.
                return b""

        while process.poll() is None:
            if time.time() > deadline:
                timeout = True
                log.info(f"Process timed out for student {self._chalk_env.student_id}")
                self._kill_group()
                process.wait()
                break
            chunk = read()
            if chunk:
                feed(chunk)
            else:
                time.sleep(dt)

        # The process may exit with output still in the pty buffer.
        while chunk := read():
            feed(chunk)

        buf = buf.rstrip(b"\r\n")
        if buf:
            emit(buf)

        os.close(fd)
        os.close(self._slave_pty_fd)
        stdout = remove_ansi_codes("\n".join(output_lines))

        return timeout, stdout

    def _run_no_capture(self) -> bool:
        try:
            self.process.wait(self.timeout)
            timeout = False
        except subprocess.TimeoutExpired:
            log.info(f"Process timed out for student {self._chalk_env.student_id}")
            self._kill_group()
            self.process.wait()
            timeout = True
        finally:
            os.close(self._master_pty_fd)
            os.close(self._slave_pty_fd)

        return timeout

    def _get_shell_command(self, script_path: Path) -> str:
        """
        Get the shell command to run the script.

        This is a separate method so that it can be overridden in tests.
        """
        if script_path.suffix == ".py":
            with open(script_path, encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("#!"):
                    return f"{script_path}"
                else:
                    return f"{sys.executable} {script_path}"
            return f"{sys.executable} {script_path}"
        return f"{script_path}"

    def read_result(self) -> Graded | None:
        """
        Read the result the script wrote to $CHALK_RESULT, or None if it wrote
        nothing.

        The output of the script is never parsed for a result: it may contain
        text controlled by the student.

        This method should only be called after the script has finished running.
        """
        if not self.result_path.is_file():
            return None
        return self._result_reader(self.result_path)


@dataclass(frozen=True)
class Sandbox:
    """
    Options of the bwrap sandbox around the script.
    """

    network: bool = False
    readable: tuple[Path, ...] = ()
    #: (source, target) files mounted read only over the working directory.
    overlays: tuple[tuple[Path, Path], ...] = ()
    #: Directories replaced by empty tmpfs mounts, besides sandbox.HIDDEN.
    hidden: tuple[Path, ...] = ()


@dataclass
class ChalkEnv:
    """
    Describes information that is passed to the autograder script as environment
    variables.
    """

    #: The answer as text; for a directory, its path.
    answer: str
    answer_path: str
    question_id: str
    quiz_id: str
    student_id: str
    pass_env: tuple[str, ...] = ()

    def to_env_dict(self, path: Path, result: Path) -> dict[str, str]:
        """
        Create the environment variables to be passed to the autograder script
        for a job executed from the given path, writing its result to the
        given file.

        Only the variables in PASS_ENV and in pass_env come from chalk's own
        environment.
        """

        base = {
            "CHALK_ROOT": str(path),
            "CHALK_RESULT": str(result),
            "CHALK_ANSWER": self.answer_path,
            "CHALK_ANSWER_CONTENT": self.answer,
            "CHALK_STUDENT": self.student_id,
            "CHALK_QUESTION": self.question_id,
            "CHALK_QUIZ": self.quiz_id,
            "CHALK_ASSIGNMENT": self.quiz_id,  # deprecated alias of CHALK_QUIZ
        }

        for var in (*PASS_ENV, *self.pass_env):
            if var in os.environ:
                base[var] = os.environ[var]
        return base


def memory_feedback(events: Events) -> str:
    if events.limit is None:
        return "The answer used more memory than it may."
    return f"The answer used more than {events.limit // 2**20} MiB of memory."


def remove_ansi_codes(src: str) -> str:
    """
    Remove ANSI escape codes from the given string.
    """
    return ANSI_REGEX.sub("", src)
