from __future__ import annotations

import os
import pty
import re
import resource
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

from chalk.core import disqualification as dq

from ..core import Disqualification, QuestionId, QuizId, StudentId, models
from ..core.answer import AnyAnswer, serialize_any_answer
from ..core.grader import Graded
from ..core.score import Score
from .repo import Repo
from .result_extractor import extract_result_from_file

__all__ = [
    "ChalkEnv",
    "Result",
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
ANSI_REGEX = re.compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")


@dataclass
class Result:
    return_code: int
    score: Score | Disqualification
    feedback: str | None = None
    stdout: str | None = None

    def __bool__(self) -> bool:
        return self.return_code == 0


class ScriptRunner:
    """
    Run an autograder script in a subprocess and extract the feedback and the
    grade from the generated report file.
    """

    def __init__(
        self,
        script_path: Path,
        repo: Repo,
        /,
        *,
        env: ChalkEnv,
        timeout: float,
        on_output_line: Callable[[str], Any] | None = None,
        capture_output: bool = True,
        limits: models.Limits | None = None,
    ) -> None:
        self._chalk_env = env
        self.timeout = timeout
        self.script_path = script_path
        self._repo = repo
        self._on_output_line = on_output_line or (lambda _: None)
        self._result: Result | None = None

        if not script_path.exists():
            raise OSError(f"Script not found: {script_path}")
        elif not script_path.is_file():
            raise OSError(f"Script is not a file: {script_path}")
        # elif not os.access(script_path, os.X_OK):
        #     raise OSError(f"Script is not executable: {script_path}")

        self._master_pty_fd, self._slave_pty_fd = pty.openpty()
        self.capture_output = capture_output

        # The result file lives outside the working directory, where the
        # student's code cannot reach it once the run is sandboxed.
        self._result_dir = Path(tempfile.mkdtemp(prefix="chalk-result-"))
        self.result_path = self._result_dir / "result"

        self.process = subprocess.Popen(
            self._get_shell_command(script_path),
            shell=True,
            cwd=repo.root,
            env=self._chalk_env.to_env_dict(repo.root, self.result_path),
            stdout=self._slave_pty_fd if capture_output else None,
            stderr=self._slave_pty_fd if capture_output else None,
            stdin=subprocess.DEVNULL,
            # Own process group, so a timeout kills the whole tree and not
            # only the shell.
            start_new_session=True,
            preexec_fn=_rlimit_setter(limits) if limits else None,
        )

    def __del__(self) -> None:
        self._kill_group()
        shutil.rmtree(getattr(self, "_result_dir", ""), ignore_errors=True)

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
        self._repo.write_file("chalk.stdout", stdout)

        # The script may hang (timeout=True), and even so it may generate a valid report file.
        # We test this here and only create a timeout score if the report file is not generated.
        result = self.read_result()
        if self.result_path.exists():
            shutil.copyfile(self.result_path, self._repo.root / "chalk.result")
        shutil.rmtree(self._result_dir, ignore_errors=True)

        if result is None:
            msg = f"Process terminated without generating report file for student {self._chalk_env.student_id}"
            log.warning(msg)

            if timeout:
                return Result(-1, score=dq.Timeout(), stdout=stdout)

            return Result(
                return_code=-1,
                score=dq.Error(),
                feedback="The autograder script failed to generate a report file.",
                stdout=stdout,
            )

        return Result(
            return_code=self.process.returncode,
            stdout=stdout,
            feedback=result.feedback,
            score=result.score,
        )

    def _run_to_stdout(self) -> tuple[bool, str]:
        deadline = (self.timeout or float("inf")) + time.time()
        process = self.process

        timeout = False
        dt = 0.025
        output_lines = []
        buf = b""
        os.set_blocking(self._master_pty_fd, False)

        def consume_buf():
            nonlocal buf
            line = buf.removesuffix(b"\r").decode(errors="replace")
            self._on_output_line(line)
            output_lines.append(line)
            buf = b""

        while process.poll() is None:
            if time.time() > deadline:
                timeout = True
                log.info(f"Process timed out for student {self._chalk_env.student_id}")
                self._kill_group()
                process.wait()
                break

            try:
                char = os.read(self._master_pty_fd, 1)
            except BlockingIOError:
                time.sleep(dt)
                continue

            if char == b"\n":
                consume_buf()
            else:
                buf += char

        buf = buf.rstrip(b"\r\n")
        if buf:
            consume_buf()

        os.close(self._master_pty_fd)
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
        return extract_result_from_file(self.result_path)


@dataclass
class ChalkEnv:
    """
    Describes information that is passed to the autograder script as environment
    variables.
    """

    answer: AnyAnswer
    answer_path: str
    question_id: QuestionId
    quiz_id: QuizId
    student_id: StudentId
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
            "CHALK_ANSWER_CONTENT": serialize_any_answer(self.answer),
            "CHALK_STUDENT": self.student_id,
            "CHALK_QUESTION": self.question_id,
            "CHALK_ASSIGNMENT": self.quiz_id,
        }

        for var in (*PASS_ENV, *self.pass_env):
            if var in os.environ:
                base[var] = os.environ[var]
        return base


def _rlimit_setter(limits: models.Limits) -> Callable[[], None] | None:
    """
    Function that applies the given limits in the child process, before the
    script starts. The limits are inherited by every process the script
    starts.
    """
    pairs = [
        (resource.RLIMIT_AS, limits.memory),
        (resource.RLIMIT_FSIZE, limits.file_size),
    ]
    pairs = [(kind, int(value)) for kind, value in pairs if value is not None]
    if not pairs:
        return None

    def apply() -> None:
        for kind, value in pairs:
            resource.setrlimit(kind, (value, value))

    return apply


def remove_ansi_codes(src: str) -> str:
    """
    Remove ANSI escape codes from the given string.
    """
    return ANSI_REGEX.sub("", src)
