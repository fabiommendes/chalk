import subprocess
from dataclasses import dataclass
from pathlib import Path

from chalk.core import disqualification as dq

from ..core import Answer, AssignmentId, Grade, QuestionId, StudentId
from .repo import Repo
from .util import extract_result, render_answer

__all__ = [
    "ChalkEnv",
    "Result",
    "ScriptRunner",
]


@dataclass
class Result:
    return_code: int
    grade: Grade | None = None
    feedback: str | None = None
    output: str | None = None

    def __bool__(self) -> bool:
        return self.return_code == 0


@dataclass
class ChalkEnv:
    """
    Describes information that is passed to the autograder script as environment
    variables.
    """

    answer: Answer
    answer_path: str
    question_id: QuestionId
    assignment_id: AssignmentId
    student_id: StudentId
    report_file: str = "report.json"

    def to_env_dict(self, path: Path) -> dict[str, str]:
        """
        Create the environment variables to be passed to the autograder script
        for a job executed from the given path.
        """

        return {
            "CHALK_DIRECTORY": str(path),
            "CHALK_RESULT_PATH": str(path / self.report_file),
            "CHALK_RESULT_FILE": self.report_file,
            "CHALK_ANSWER_PATH": str(path / self.answer_path),
            "CHALK_ANSWER": render_answer(self.answer),
            "CHALK_STUDENT": self.student_id,
            "CHALK_QUESTION": self.question_id,
            "CHALK_ASSIGNMENT": self.assignment_id,
        }


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
        env: ChalkEnv,
        *,
        capture_stdout: bool = True,
        timeout: float | None = None,
    ) -> None:
        self._chalk_env = env
        self.timeout = timeout
        self.script_path = script_path
        self._repo = repo
        self._finished = False

        self.process = subprocess.Popen(
            str(self.script_path.absolute()),
            shell=True,
            cwd=repo.base_path,
            env=self._chalk_env.to_env_dict(repo.base_path),
            stdout=subprocess.PIPE if capture_stdout else None,
            stderr=subprocess.STDOUT if capture_stdout else None,
        )

    def run(self) -> Result:
        if self._finished:
            raise RuntimeError("Script has already finished running.")

        def stdout() -> None | str:
            if self.process.stdout is None:
                return None
            return self.process.stdout.read().decode()

        self._finished = True
        try:
            retcode = self.process.wait(self.timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            return Result(
                return_code=-1,
                grade=Grade(0, disqualification=dq.Timeout()),
                output=stdout(),
            )
        except subprocess.SubprocessError:
            self.process.kill()
            return Result(
                return_code=-1,
                grade=Grade(0, disqualification=dq.Invalid()),
                output=stdout(),
            )

        if retcode == 0:
            grade, feedback = extract_result(
                self._repo.base_path / self._chalk_env.report_file
            )
        else:
            grade, feedback = None, None

        return Result(
            return_code=retcode,
            output=stdout(),
            feedback=feedback,
            grade=grade,
        )
