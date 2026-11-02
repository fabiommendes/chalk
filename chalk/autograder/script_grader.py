import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Any

from ..core import Question, StudentId, models
from ..core.grader import DEFAULT_TIMEOUT, Graded, Grader
from .repo import Repo
from .script_runner import ChalkEnv, ScriptRunner

NOT_GIVEN: Any = object()

log = getLogger(__name__)


@dataclass(frozen=True)
class ScriptGrader(Grader[str | Path]):
    """
    Grades based on a regular expression.

    The answer is considered correct if it matches the regex.
    """

    script: Path
    question: Question
    conf: models.Autograder

    def __call__(
        self,
        id: StudentId,
        answer: str | Path,
        /,
        *,
        debug: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
        keep_files: bool = False,
        keep_failed: bool = False,
        on_output_line: Callable[[str], None] | None = None,
        capture_output: bool = True,
        **kwargs,
    ) -> Graded | None:

        if isinstance(answer, Path):
            if not answer.exists():
                log.warning(f"Answer path {answer} does not exist for student {id}")
                return None
            elif answer.is_file():
                answer = data = answer.read_text()
            else:
                data = str(answer)
        else:
            data = answer

        with self.student_repository(id, answer, clear=not keep_files and not keep_failed) as repo:
            runner = ScriptRunner(
                self.script,
                repo,
                env=ChalkEnv(
                    answer=data,
                    answer_path=str(self._answer_path()),
                    question_id=self.question.id,
                    quiz_id=self.question.quiz.id,
                    student_id=id,
                    pass_env=tuple(self.conf.pass_env),
                ),
                timeout=timeout,
                on_output_line=on_output_line,
                capture_output=capture_output,
            )
            result = runner.run()

        if result.return_code != 0 and debug:
            msg = f"[red]Autograder process  for student {id} with code {result.return_code}[/red]"
            log.warning(msg)

        return Graded(
            result.score,
            feedback=result.feedback,
        )

    @contextmanager
    def student_repository(
        self, student_id: StudentId, answer: str | Path, /, clear: bool = True
    ) -> Any:
        """
        Context manager that creates a isolated student repository within the
        student's submission directories.

        It also copies the answer to a file within the repository and copy (or link)
        all files in the template repository, if it exists.
        """
        # Create a new repository for student
        tmp_dir = tempfile.TemporaryDirectory(prefix=f"chalk-{student_id}-", delete=clear)
        repo = Repo(Path(tmp_dir.name))

        try:
            template = self.question.get_template_path()
            student_repo = answer if isinstance(answer, Path) and answer.is_dir() else None

            answer_content = None
            if isinstance(answer, Path) and answer.is_file():
                answer_content = answer.read_bytes()
            elif isinstance(answer, str):
                answer_content = answer.encode("utf-8")

            if template or student_repo:
                # Never link: the student code could write through a hard link
                # and change the template for everyone graded afterwards.
                repo.sync_template(template=template, student_repo=student_repo, copy_mode="copy")
                log.debug(f"Copied template repository for {student_id}")

            repo.write_file(
                "chalk.info",
                self.chalk_info(
                    pwd=str(repo.root),
                    student_id=student_id,
                    template_path=str(template) if template else "<none>",
                    student_repo_path=str(student_repo) if student_repo else "<none>",
                    answer_content="<provided>" if answer_content is not None else "<none>",
                    answer_size=f"{len(answer_content) // 1024} kb"
                    if answer_content is not None
                    else "0",
                ),
            )

            if answer_content is not None:
                repo.write_file(self._answer_path(), answer_content)
                log.debug(f"Copied answer for {student_id}")

            yield repo
        finally:
            if clear:
                repo.clear_all()
                log.debug(f"Cleared repository for {student_id}")

    def chalk_info(self, **kwargs: str) -> str:
        """
        Generate a chalk.info file for the student repository.
        """
        info = {
            "question_id": self.question.id,
            "quiz_id": self.question.quiz.id,
            "answer_path": self._answer_path(),
            **kwargs,
        }
        lines = ["Chalk Info:"]
        lines.extend(f"  {key}: {value}" for key, value in info.items())

        return "\n".join(lines)

    def _answer_path(self) -> str:
        return str(self.conf.answer or "answer.txt")
