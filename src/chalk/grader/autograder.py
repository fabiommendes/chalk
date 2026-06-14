import re
from contextlib import contextmanager
from logging import getLogger
from pathlib import Path
from typing import Generator, Iterable

import opt
from natsort import natsorted

from ..core import (
    Answer,
    AssignmentId,
    Disqualification,
    Grade,
    QuestionId,
    Response,
    StudentId,
    disqualification,
)
from .conf import AutograderConf
from .grader import Grader
from .repo import Repo
from .runners import ChalkEnv, ScriptRunner
from .validators import ResponseValidator, get_validator_from_extension

NOT_SETUP_MSG = "Autograder is not set up. Maybe you forgot to call .prepare()?"
RUN_AUTOGRADER_SCRIPT_REGEX = re.compile(r"_?run(-[0-9]+)?-autograde")
CLEAR_PATHS = {".git", ".venv", ".pytest_cache", "node_modules", "__pycache__"}

log = getLogger(__name__)


class Autograder(Grader[Answer]):
    @property
    def base_path(self) -> Path:
        return self._base_path

    @property
    def question_id(self) -> QuestionId:
        return self._question_id

    @property
    def assignment_id(self) -> AssignmentId:
        return self._assignment_id

    def __init__(
        self,
        assignment_id: AssignmentId,
        question_id: QuestionId,
        base: Path,
        clear: bool = True,
        always_clear: bool | Iterable[str | Path] = True,
        prefer_links: bool = False,
        debug: bool = False,
    ) -> None:
        self.debug = debug

        self._assignment_id = assignment_id
        self._question_id = question_id
        self._base_path = base

        self._repositories: dict[StudentId, Repo] = {}
        self._clear_temporary_files = clear
        self._prefer_links = prefer_links

        if always_clear is True:
            self._always_clear = CLEAR_PATHS
        elif always_clear is False:
            self._always_clear = set()
        else:
            self._always_clear = set(map(str, always_clear))

        # Attributes that will be initialized later in the prepare() method
        self._conf = AutograderConf()
        self._validators: list[ResponseValidator] = []

    def prepare(self) -> None:
        """
        Prepare the autograder for execution, which may involve setting up the
        environment, loading test cases, etc.
        """
        base_path = self._base_path
        if not base_path.exists():
            msg = f"Base path {base_path} does not exist"
            msg += f"\nCreate a new autograder with `chalk autograde init {self._assignment_id} {self._question_id}`"
            raise FileNotFoundError(msg)

        # Load the autograder configuration file, if it exists.
        conf_path = self.get_conf_path()
        if conf_path is not None:
            self._conf = AutograderConf.from_conf_path(conf_path)

        # Find validators and append them to the pipeline.
        self._validators = self._find_validators()

    def qualify(
        self, response: Response, student_id: StudentId
    ) -> Disqualification | None:
        reason = None
        for validator in self._validators:
            disqualification.merge(reason, validator(response, student_id))
        return reason

    def autograde(self, response: Response, student_id: StudentId) -> None:
        """
        Validate the response and update it with the computed grade and feedback
        if it is valid.
        """
        if error := self.qualify(response, student_id):
            response.grade = Grade(0, disqualification=error)
        else:
            self.update_response(response, student_id)

    def update_response(self, response: Response, student_id: StudentId) -> None:
        """
        Update the given response with the computed grade and feedback.
        """

        # Skip empty answers
        if response.answer is None:
            msg = f"Empty answer for student {student_id}, at {self._assignment_id}/{self._question_id}"
            log.info(msg)
            return

        # Run autograder scripts and update the response with the results
        with self._create_student_repository(student_id, response.answer) as repo:
            for script_path in self.get_autograder_scripts():
                runner = ScriptRunner(
                    script_path,
                    repo,
                    env=ChalkEnv(
                        answer=response.answer,
                        answer_path=str(self._get_answer_path()),
                        question_id=self.question_id,
                        assignment_id=self.assignment_id,
                        student_id=student_id,
                    ),
                    timeout=self._conf.timeout,
                    capture_stdout=not self.debug,
                )

                result = runner.run()
                response.grade = opt.coalesce(result.grade, response.grade)
                response.feedback = opt.coalesce(result.feedback, response.feedback)

                if result.return_code != 0 and self.debug:
                    msg = f"[red]Autograder failed for student {student_id} with code {result.return_code}[/red]"
                    log.warning(msg)

    #
    # Interact with teacher-defined resources
    #
    def get_template_repo_path(self) -> Path | None:
        """
        Get the path to the template repository for this question, if it exists.

        The repo should be located at either _autograde.repo or autograde.repo
        within the base path.
        """
        names = ("_autograde.repo", "autograde.repo")
        return self._get_path_from_names(names, is_dir=True)

    def get_conf_path(self) -> Path | None:
        """
        Get the path to the autograder configuration file, if it exists.

        The configuration file should be located at autograde.conf within the base path.
        """
        names = ("_autograde.conf", "autograde.conf")
        return self._get_path_from_names(names, is_dir=False)

    def get_autograder_scripts(self) -> list[Path]:
        """
        Get a list of paths to autograder scripts within the base path.

        Autograder scripts should be located in the autograde.scripts directory within the base path.
        """
        files = {
            p
            for p in self._base_path.iterdir()
            if p.is_file() and RUN_AUTOGRADER_SCRIPT_REGEX.match(p.name)
        }
        return natsorted(files, key=lambda p: p.name.lower())

    #
    # Utility methods
    #
    def _get_path_from_names(
        self,
        names: Iterable[str],
        is_dir: bool = False,
    ) -> Path | None:
        """
        Get the path to the first existing file or directory with the given names
        within the base path.
        """
        for name in names:
            path = self.base_path / name
            if path.exists() and path.is_dir() == is_dir:
                return path
        return None

    def _get_answer_path(self) -> Path:
        if self._conf.answer is not None:
            return self._conf.answer
        return self.base_path / "answer.txt"

    def _get_student_repository(self, student_id: StudentId) -> Repo:
        if student_id not in self._repositories:
            dest = self.base_path / student_id
            dest.mkdir(parents=True, exist_ok=True)
            self._repositories[student_id] = repo = Repo(dest)
            return repo

        return self._repositories[student_id]

    @contextmanager
    def _create_student_repository(
        self,
        student_id: StudentId,
        answer: Answer,
    ) -> Generator[Repo]:
        """
        Context manager that creates a isolated student repository within the
        student's submission directories.

        It also copies the answer to a file within the repository and copy (or link)
        all files in the template repository, if it exists.
        """
        repo = self._get_student_repository(student_id)

        # Copy the template repository
        template = self.get_template_repo_path()
        if template is not None:
            repo.copy_source(template, link=self._prefer_links)
            log.debug(f"Copied template repository for {student_id}")

        # Copy the answer to the student's repository
        if answer is None:
            msg = f"Empty answer for student {student_id}, at {self._assignment_id}/{self._question_id}"
            raise ValueError(msg)
        repo.write_file(self._get_answer_path(), answer)
        log.debug(f"Copied answer for {student_id}")

        # Yield the repository for grading and cleanup afterwards
        try:
            yield repo
        finally:
            for path in self._always_clear:
                repo.force_remove(path)
            if self._clear_temporary_files:
                repo.clear()

    def _find_validators(self) -> list[ResponseValidator]:
        """
        Find all validator functions in the autograder repository and return them as a list.
        """
        validators: list[ResponseValidator] = []

        # Add automatic validators based on the answer file extension
        if self._conf.validate_syntax is True:
            suffix = self._get_answer_path().suffix
            opt.map(validators.append, get_validator_from_extension(suffix))
        elif isinstance(self._conf.validate_syntax, str):
            validator = get_validator_from_extension(self._conf.validate_syntax)
            if validator is None:
                msg = f"Invalid option: validate_syntax = {self._conf.validate_syntax}"
                msg += "\nUnknown file extension."
                raise ValueError(msg)
            validators.append(validator)

        # TODO: Implement validator discovery logic. This may involve looking for specific files, parsing them, etc.

        return validators
