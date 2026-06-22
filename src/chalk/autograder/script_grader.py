from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from logging import getLogger
from pathlib import Path
from typing import Any, Callable

import opt

from ..core import AssignmentId, QuestionId, StudentId
from ..core.grader import Graded, Grader
from ..util.path import get_path_from_names
from .conf import AutograderConf
from .repo import Repo
from .script_runner import ChalkEnv, ScriptRunner

NOT_GIVEN: Any = object()

log = getLogger(__name__)


@dataclass(frozen=True)
class ScriptGrader(Grader[str]):
    """
    Grades based on a regular expression.

    The answer is considered correct if it matches the regex.
    """

    root: Path
    script: Path
    question_id: QuestionId
    assignment_id: AssignmentId
    grade: Decimal
    validator: Callable[[str], bool] | None = None
    template_repo: Path | None = NOT_GIVEN
    conf: AutograderConf = NOT_GIVEN
    keep_files: bool = False
    debug: bool = False

    def __post_init__(self) -> None:
        if self.conf is NOT_GIVEN:
            conf = AutograderConf.from_root_path(self.root) or AutograderConf()
            object.__setattr__(self, "conf", conf)

        if self.template_repo is NOT_GIVEN:
            template_repo = get_path_from_names(
                self.root,
                ("_template", "autograde.template", "_autograde.template"),
                accept_dir=True,
            )
            object.__setattr__(self, "template_repo", template_repo)

    def __call__(
        self,
        id: StudentId,
        answer: str,
        /,
        **kwargs: Any,
    ) -> Graded | None:

        with self.student_repository(id, answer) as repo:
            runner = ScriptRunner(
                self.script,
                repo,
                env=ChalkEnv(
                    answer=answer,
                    answer_path=str(self._answer_path()),
                    question_id=self.question_id,
                    assignment_id=self.assignment_id,
                    student_id=id,
                ),
                timeout=self.conf.timeout,
                capture_stdout=not self.debug,
            )

            result = runner.run()

            if result.return_code != 0 and self.debug:
                msg = f"[red]Autograder failed for student {id} with code {result.return_code}[/red]"
                log.warning(msg)
            if result.return_code != 0:
                return None
            return Graded(
                opt.map(lambda x: x * self.grade, result.score),
                feedback=result.feedback,
            )

        raise 1

    @contextmanager
    def student_repository(self, student_id: StudentId, answer: str, /) -> Any:
        """
        Context manager that creates a isolated student repository within the
        student's submission directories.

        It also copies the answer to a file within the repository and copy (or link)
        all files in the template repository, if it exists.
        """
        # Create a new repository for student
        repo_path = self.root / student_id
        repo_path.mkdir(parents=True, exist_ok=True)
        repo = Repo(repo_path)

        try:
            # Copy the template repository
            if self.template_repo is not None:
                repo.copy_source(self.template_repo, link=self.conf.prefer_links)
                log.debug(f"Copied template repository for {student_id}")

            # Copy the answer to the student's repository
            if answer is None:
                msg = f"Empty answer for student {student_id}, at {self._assignment_id}/{self._question_id}"
                raise ValueError(msg)
            repo.write_file(self._answer_path(), answer)
            log.debug(f"Copied answer for {student_id}")

            # Yield the repository for grading and do cleanup afterwards
            yield repo
        finally:
            for path in self.conf.clear:
                repo.force_remove(path)

            if not self.keep_files and self.conf.clear_temporaries:
                repo.clear_tracked()

    def _answer_path(self) -> str:
        return str(self.conf.answer) or "answer.txt"
