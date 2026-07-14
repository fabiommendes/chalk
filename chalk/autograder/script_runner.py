from __future__ import annotations

import os
import pty
import re
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Any, Callable

from chalk.core import disqualification as dq

from ..core import Disqualification, QuestionId, QuizId, StudentId
from ..core.answer import AnyAnswer, serialize_answer
from ..core.grader import Graded
from ..core.score import Score
from .repo import Repo
from .result_extractor import extract_result_from_file
from .result_parser import parse_result_from_stdout

__all__ = [
    "ChalkEnv",
    "Result",
    "ScriptRunner",
]
log = getLogger(__name__)

REEXPORT_VARIABLES = ["PATH", "LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME"]
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

        self.process = subprocess.Popen(
            self._get_shell_command(script_path),
            shell=True,
            cwd=repo.root,
            env=self._chalk_env.to_env_dict(repo.root),
            stdout=self._slave_pty_fd,
            stderr=self._slave_pty_fd,
            stdin=subprocess.DEVNULL,
        )

    def __del__(self) -> None:
        try:
            self.process.kill()
        except Exception:
            pass

    def run(self) -> Result:
        if self._result is not None:
            return self._result

        deadline = (self.timeout or float("inf")) + time.time()
        process = self.process
        output_lines = []

        timeout = False
        dt = 0.025
        buf: bytes = b""
        lines: deque[bytes] = deque()

        def worker():
            nonlocal buf
            try:
                data = os.read(self._master_pty_fd, 1024)
            except OSError:
                if buf:
                    lines.appendleft(buf)
                buf = b""
            else:
                buf = b""
                endline = data.endswith(b"\n")
                read_lines = data.splitlines()
                read_lines[0] = buf + read_lines[0]
                if not endline:
                    buf = read_lines.pop()
                for line in reversed(read_lines):
                    lines.appendleft(line)

        def consume():
            while lines:
                line = lines.pop().removesuffix(b"\r").decode(errors="replace")
                output_lines.append(line)
                self._on_output_line(line)

        while process.poll() is None:
            time.sleep(dt)
            while True:
                thread = threading.Thread(target=worker)
                thread.start()
                try:
                    thread.join(timeout=deadline - time.time())
                except TimeoutError:
                    break
                if not buf:
                    break
                consume()

                if time.time() > deadline:
                    timeout = True
                    log.info(f"Process timed out for student {self._chalk_env.student_id}")
                    process.kill()
                    break

        consume()

        if buf:
            line = buf.decode(errors="replace")
            output_lines.append(line)
            self._on_output_line(line)

        os.close(self._master_pty_fd)
        os.close(self._slave_pty_fd)
        stdout = remove_ansi_codes("\n".join(output_lines))
        self._repo.write_file("chalk.stdout", stdout)

        # The script may hang (timeout=True), and even so it may generate a valid report file.
        # We test this here and only create a timeout score if the report file is not generated.
        if (result := self.read_result(stdout)) is None:
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

    def _get_shell_command(self, script_path: Path) -> str:
        """
        Get the shell command to run the script.

        This is a separate method so that it can be overridden in tests.
        """
        if script_path.suffix == ".py":
            with open(script_path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("#!"):
                    return f"{script_path}"
                else:
                    return f"{sys.executable} {script_path}"
            return f"{sys.executable} {script_path}"
        return f"{script_path}"

    def read_result(self, stdout: str | None = None) -> Graded | None:
        """
        Get the result of the script execution.

        This method should only be called after the script has finished running.
        """
        report_file = self._chalk_env.find_result_file(self._repo.root)

        result: Graded | None = None
        if report_file:
            result = extract_result_from_file(report_file)
        if result is None and stdout:
            result = parse_result_from_stdout(stdout)
        return result


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
    result_file: str = "graded.*"

    def to_env_dict(self, path: Path, keep_env: bool = True) -> dict[str, str]:
        """
        Create the environment variables to be passed to the autograder script
        for a job executed from the given path.
        """

        report = self.result_file
        if report.endswith(".*"):
            report = report[:-2] + ".json"

        base = {
            "CHALK_ROOT": str(path),
            "CHALK_RESULT": report,
            "CHALK_ANSWER": self.answer_path,
            "CHALK_ANSWER_CONTENT": serialize_answer(self.answer),
            "CHALK_STUDENT": self.student_id,
            "CHALK_QUESTION": self.question_id,
            "CHALK_ASSIGNMENT": self.quiz_id,
        }

        for var in os.environ if keep_env else REEXPORT_VARIABLES:
            if var in os.environ:
                base[var] = os.environ[var]
        return base

    def find_result_file(self, base: Path) -> Path | None:
        """
        Find the result file generated by the autograder script in the given path.
        """
        for file in base.glob(self.result_file):
            if file.is_file():
                return file
        return None


def remove_ansi_codes(src: str) -> str:
    """
    Remove ANSI escape codes from the given string.
    """
    return ANSI_REGEX.sub("", src)
