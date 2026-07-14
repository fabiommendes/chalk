import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Any, Callable

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
                ),
                timeout=timeout,
                on_output_line=on_output_line,
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
            if (template := self.question.get_template_path()) is not None:
                repo.copy_tree(template)
                log.debug(f"Copied template repository for {student_id}")

            if isinstance(answer, str):
                repo.write_file(self._answer_path(), answer)
            elif isinstance(answer, Path) and answer.is_file():
                repo.write_file(self._answer_path(), answer.read_bytes())
            else:
                repo.copy_tree(answer)

            log.debug(f"Copied answer for {student_id}")

            yield repo
        finally:
            if clear:
                repo.clear_all()
                log.debug(f"Cleared repository for {student_id}")

    def _answer_path(self) -> str:
        return str(self.conf.answer or "answer.txt")
