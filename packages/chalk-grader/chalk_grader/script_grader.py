import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Any

from . import disqualification as dq
from . import models
from .graded import DEFAULT_TIMEOUT, Graded
from .repo import Repo
from .sandbox import check_bwrap
from .script_runner import ChalkEnv, Result, Sandbox, ScriptRunner
from .task import Task

NOT_GIVEN: Any = object()

log = getLogger(__name__)


@dataclass(frozen=True)
class ScriptGrader:
    """
    Grades an answer with the autograder script of the question.

    The answer is copied to a working directory together with the template,
    and the script writes the result to $CHALK_RESULT.
    """

    script: Path | None
    task: Task
    conf: models.Autograder

    def __call__(
        self,
        id: str,
        answer: str | Path,
        /,
        *,
        debug: bool = False,
        timeout: float | None = None,
        keep_files: bool = False,
        keep_failed: bool = False,
        on_output_line: Callable[[str], None] | None = None,
        capture_output: bool = True,
        **kwargs,
    ) -> Graded | None:

        if timeout is None:
            timeout = self.conf.timeout or DEFAULT_TIMEOUT
        sandbox = self._sandbox()

        limit = self.conf.limits.answer_size
        if isinstance(answer, Path):
            if not answer.exists():
                log.warning(f"Answer path {answer} does not exist for student {id}")
                return None
            elif answer.is_file():
                if answer.stat().st_size > limit:
                    return answer_too_large(limit)
                answer = data = answer.read_text()
            else:
                data = str(answer)
        else:
            if len(answer.encode()) > limit:
                return answer_too_large(limit)
            data = answer

        with self.student_repository(id, answer, clear=not keep_files and not keep_failed) as repo:
            result = self.run_in(
                repo,
                env=ChalkEnv(
                    answer=data,
                    answer_path=str(self._answer_path()),
                    question_id=self.task.question_id,
                    quiz_id=self.task.quiz_id,
                    student_id=id,
                    pass_env=tuple(self.conf.pass_env),
                ),
                timeout=timeout,
                on_output_line=on_output_line,
                capture_output=capture_output,
                sandbox=sandbox,
            )

        if result.return_code != 0 and debug:
            msg = f"[red]Autograder process  for student {id} with code {result.return_code}[/red]"
            log.warning(msg)

        if result.score is None:
            return None
        return Graded(
            result.score, feedback=result.feedback, notes=result.notes, cases=result.cases
        )

    def run_in(
        self,
        repo: Repo,
        /,
        *,
        env: ChalkEnv,
        timeout: float,
        on_output_line: Callable[[str], None] | None,
        capture_output: bool,
        sandbox: Sandbox | None,
    ) -> Result:
        """
        Grade the answer prepared in the given repository.
        """
        assert self.script is not None
        return ScriptRunner(
            self.script,
            repo,
            env=env,
            timeout=timeout,
            on_output_line=on_output_line,
            capture_output=capture_output,
            limits=self.conf.limits,
            sandbox=sandbox,
        ).run()

    @contextmanager
    def student_repository(
        self, student_id: str, answer: str | Path | None, /, clear: bool = True
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
            template = self.task.template
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

    def _sandbox(self) -> Sandbox | None:
        """
        Sandbox options for this question, or None to run without sandbox.
        """
        kind = self.conf.sandbox or "bwrap"
        if kind == "none":
            return None
        if kind != "bwrap":
            raise NotImplementedError(f"sandbox {kind!r} is not implemented yet")
        check_bwrap()
        root = self.task.root
        mounts = tuple(root / p.expanduser() for p in self.conf.mounts)
        return Sandbox(network=self.conf.network == "host", readable=mounts)

    def chalk_info(self, **kwargs: str) -> str:
        """
        Generate a chalk.info file for the student repository.
        """
        info = {
            "question_id": self.task.question_id,
            "quiz_id": self.task.quiz_id,
            "answer_path": self._answer_path(),
            **kwargs,
        }
        lines = ["Chalk Info:"]
        lines.extend(f"  {key}: {value}" for key, value in info.items())

        return "\n".join(lines)

    def _answer_path(self) -> str:
        return str(self.conf.answer or "answer.txt")


def answer_too_large(limit: int) -> Graded:
    return Graded(dq.InvalidInput(), feedback=f"The answer is larger than {limit} bytes.")
