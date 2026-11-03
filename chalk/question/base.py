from __future__ import annotations

import sys
from abc import abstractmethod
from collections.abc import Callable, Iterable, Iterator
from decimal import Decimal
from logging import getLogger
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Literal,
    assert_never,
    final,
    overload,
)
from weakref import ref

import errorz as rz
import opt
from pydantic import Field

from ..core import models
from ..core.answer import serialize_any_answer
from ..core.grader import Graded, Grader
from ..core.issue import Issue, IssueLevel, IssueLevelLike, list_of_issues
from ..core.models import AnyAnswer, Autograder, QuestionId, QuestionType, StudentId
from ..data import json, yaml
from ..util import unpack
from .renderable import RenderableQuestion

if TYPE_CHECKING:
    from ..core.classroom import Classroom
    from ..core.quiz import Quiz
    from ..question import Question

log = getLogger(__name__)

type QuestionScope = Literal["grading", "display", "validation", "response"]
type OK = Literal[True]
ok: OK = True


__all__ = [
    "BaseQuestion",
    "validate_type",
    "type_error",
    "fail",
    "empty_result",
    "is_empty_issue",
]


class BaseQuestion[Conf: models.BaseQuestion, Answer: AnyAnswer](RenderableQuestion):
    _conf: Conf

    @property
    def id(self) -> QuestionId:
        return self._id

    @property
    def conf(self) -> Conf:
        return self._conf

    @property
    def name(self) -> str:
        return self._conf.name or self.id

    @name.setter
    def name(self, value: str) -> None:
        self._conf.name = value

    @property
    def stem(self) -> str | None:
        return self._conf.stem

    @stem.setter
    def stem(self, value: str | None) -> None:
        self._conf.stem = value

    @property
    def value(self) -> Decimal:
        return self._conf.value or Decimal(1)

    @value.setter
    def value(self, value: Decimal) -> None:
        self._conf.value = value

    @property
    def autograder(self) -> Autograder:
        return self._conf.autograder or Autograder()

    @autograder.setter
    def autograder(self, value: Autograder | None) -> None:
        self._conf.autograder = value

    @property
    def type(self) -> QuestionType:
        return getattr(self._conf, "type", None)

    @property
    def quiz(self) -> Quiz:
        return unpack(
            self._quiz(),
            throw=RuntimeError("Question is not associated with a quiz."),
        )

    @property
    def classroom(self) -> Classroom:
        return self.quiz.classroom

    @property
    def answer_suffix(self) -> str | None:
        return self.get_answer_extension()

    @answer_suffix.setter
    def answer_suffix(self, value: str | None) -> None:
        self._conf.answer_suffix = value

    @property
    def root(self) -> Path:
        return self.quiz.root / self.id

    #: Classes that implement this declare that the answers can be converted to
    #: a meaningful textual representation. Strings used as labels **SHOULD NOT**
    #: be considered as text.
    answer_to_text: Annotated[Callable[[Answer], str] | None, Field(exclude=True)] = None

    def __init__(self, id: QuestionId, conf: Conf, *, quiz: Quiz):
        self._conf = conf
        self._id = id
        self._quiz = ref(quiz)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.quiz.id}/{self.id}>"

    #
    # Getter functions
    #
    def get_root(self, mkdir: bool = False) -> Path:
        """
        Get the base path for this question, which is used to store question-specific
        files such as autograder scripts, test cases, etc.

        Raises:
            * NotADirectoryError if the path exists but is not a directory.
            * FileNotFoundError if the path does not exist and mkdir is False.
        """
        path = self.quiz.root / self.id

        if path.exists() and not path.is_dir():
            msg = f"Question path is not a directory: {path}"
            raise NotADirectoryError(msg)
        if mkdir:
            path.mkdir(parents=True, exist_ok=True)
        elif not path.exists():
            msg = f"Question path does not exist: {path}"
            raise FileNotFoundError(msg)

        return path

    def get_responses_root(self, mkdir: bool = False, check: bool = False) -> Path:
        """
        Get the root path to where store answer files if the answers are to
        be stored in separate files.

        This is typically <quiz-root>/<question-id>/responses.
        """
        path = self.root / "responses"

        if path.exists() and not path.is_dir():
            msg = f"Responses path is not a directory: {path}"
            raise NotADirectoryError(msg)
        if mkdir:
            path.mkdir(parents=True, exist_ok=True)
        elif check and not path.exists():
            msg = f"Responses path does not exist: {path}"
            raise FileNotFoundError(msg)

        return path

    def get_persisted_answer(self, student_id: StudentId) -> Answer | None:
        """
        Read the answer from a local file, if it exists.

        It **DOES NOT** interact with the submissions.csv file, it only reads
        the answer from a file if it is in the question's responses directory.
        """
        root = self.get_responses_root(mkdir=False)
        if not root.exists():
            return None

        suffix = self.get_answer_suffix()
        path = root / f"{student_id}{suffix}"
        if not path.exists():
            return None
        return self.validate_answer(path.read_text())

    def persist_answer(self, student_id: StudentId, answer: Answer) -> None:
        """
        Persist the answer to a local file.

        This **DOES NOT** update the submissions.csv file, it only writes the answer
        to a file in the question's responses directory.
        """
        root = self.get_responses_root(mkdir=True)
        suffix = self.get_answer_suffix()
        path = root / f"{student_id}{suffix}"
        path.write_text(self.serialize_answer(answer))

    @overload
    def get_answer_extension(self, default: str) -> str: ...

    @overload
    def get_answer_extension(self, default: str | None = None) -> str | None: ...

    def get_answer_extension(self, default: str | None = None) -> str | None:
        """
        Get the suffix for answer files for this question, if any.

        This is used to determine the file type of answer files when reading
        them from disk.
        """
        return opt.map(
            lambda s: s.removeprefix("."),
            opt.unwrap(self._conf.answer_suffix, default),
        )

    def get_answer_suffix(self):
        """
        Get the suffix for answer files for this question, if any.

        This is used to determine the file type of answer files when reading
        them from disk.
        """
        return "." + (self.get_answer_extension() or "txt")

    def get_autograder(self) -> Autograder:
        """
        Get the autograder configuration for this question, or a default configuration if none is set.
        """
        if self._conf.autograder is not None:
            return self._conf.autograder
        if self._quiz() is not None:
            return self.quiz.get_autograder()
        return Autograder()

    def get_autograde_script(self, *, check_exists: bool = True) -> Path | None:
        """
        Get the path to the autograder script.

        If the script is not specified, return the path to the default script.
        """
        name = self.get_autograder().script
        if name is not None:
            path = self.root / name
        else:
            files = list(self.root.glob("autograde.*"))
            match files:
                case []:
                    return None
                case [file]:
                    path = file
                case _:
                    files = sorted(files, key=script_priority)
                    msg = f"multiple autograding scripts found for {self.quiz.id}/{self.id}, using {files[0]}"
                    log.warning(msg)
                    path = files[0]
        if check_exists and not path.exists():
            return None
        return path

    def get_template_path(self, *, check_exists: bool = True) -> Path | None:
        """
        Get the path to the template directory for this question, if any.

        If the template does not exist or if it is invalid, return None.
        """
        path = self.get_autograder().template or Path("template")
        if path.is_absolute():
            path = self.quiz.classroom.root / path.relative_to("/")
        else:
            path = self.root / path

        if check_exists and (not path.exists() or not path.is_dir()):
            return None
        return path

    def get_profile_grader(self) -> Grader[Any] | None:
        """
        Grader of the autograder profile that does not run a script, if the
        question declares one.
        """
        conf = self.get_autograder()
        if conf.profile == "regex":
            from ..autograder.regex_answer import RegexAnswerGrader

            return RegexAnswerGrader(conf)
        if conf.profile == "python-pytest":
            from ..autograder.pytest_profile import PytestGrader

            return PytestGrader(
                script=None, question=self, conf=conf, solution=self._profile_solution()
            )
        if conf.profile == "rust-cargo":
            from ..autograder.rust_profile import CargoGrader

            return CargoGrader(
                script=None, question=self, conf=conf, solution=self._profile_solution()
            )
        return None

    def get_reference_answer(self) -> Answer | None:
        """
        The teacher's reference answer, in the form the grader accepts, or
        None. `chalk autograde --check` expects it to get the full score.
        """
        return self.get_answer_key()

    def _profile_solution(self) -> Any:
        """
        Reference solution given to profile graders: the text of the answer,
        or a directory for repository questions.
        """
        return self.get_reference_answer()

    def get_grader(self) -> Grader[Answer] | None:
        """
        Get the default Grader object for this question, which can be used to
        validate and grade answers to the question.

        If the question do not support automatic grading, return None.
        """
        if not hasattr(self, "grade_answer"):
            return None

        def grader(id: StudentId, answer: Answer, /, **kwargs: Any) -> Graded | None:
            return self.grade_answer(answer)  # type: ignore

        return grader

    def get_answer_key(self) -> Answer | None:
        """
        Get the answer key for this question, if any.

        The answer key may be stored in the conf file or on a separate file
        depending on the question type. By default we look at <question-root>/answer_key.{ext}

        Raises:
            ValueError if the answer key exists, but its content is invalid.
        """
        ext = self.get_answer_suffix()
        path = self.root / f"answer_key{ext}"
        if path.exists():
            src = path.read_text()
            return self.validate_answer(src)

    def get_template_answers(self) -> dict[str, Answer]:
        """
        Get the template answers for this question, if any.

        It look for templates in <question-root>/answers/*.{ext} where {ext}
        is the default answer extension for this question.
        """
        base = self.root / "answers"
        if not base.exists():
            return {}

        templates = {}
        ext = self.get_answer_suffix()
        for path in base.glob(f"*{ext}"):
            templates[path.stem] = self.validate_answer(path.read_text())
        return templates

    def get_reference_from_file(self, name: str, /) -> Answer | None:
        """
        Get a reference answer from a file with the given name, if it exists.

        The file is searched for in the question's base path, which is typically
        the quiz's base path joined with the question's id.
        """
        root = self.get_root()
        path = root / name
        if not path.exists():
            return None

        if name.endswith(".yaml") or name.endswith(".yml"):
            answer = yaml.load(path.open())
        elif name.endswith(".json"):
            answer = json.load(path.open())
        else:
            answer = path.read_text(encoding="utf-8")

        return rz.unwrap(self.validate_answer(answer), None)

    #
    # Validation methods
    #
    @abstractmethod
    def validate_answer(self, answer: Any, /) -> Answer:
        """
        Validate a student answer and return a list of issues
        with the answer that may prevent it from being graded correctly.

        Should raise an ValueError if the answer is invalid.

        This method should always accept string even when the expected answer
        type is different. When possible, it should parse the strings and
        convert them to the expected answer type.
        """
        raise NotImplementedError("Must be implemented by subclasses.")

    def serialize_answer(self, answer: Answer, /) -> str:
        """
        Convert the given answer to a string representation.
        """
        return serialize_any_answer(answer)

    @final
    def validate_question(
        self,
        *,
        level: IssueLevelLike = IssueLevel.ALL,
        scope: QuestionScope | None = None,
        check_responses: bool = False,
        fix: bool = False,
        error: Literal["raise", "ignore"] = "raise",
    ) -> list[Issue]:
        """
        Validate itself under a given severity level. It may change the question
        inplace to fix issues that are fixable automatically.

        Raise a ValueError with a list of issues if it fails.

        Args:
            level:
                The severity level to validate against. Only issues with a severity
                equal to or higher than this level will be considered.
            scope:
                The scope of issues to validate against. Only issues within this
                scope will be considered.
            check_responses:
                If True, responses will be validated as well.
            fix:
                If True, fixable issues will be automatically fixed.

        See also:
            * func:`BaseQuestion.iter_issues` for a more detailed list of issues.
        """
        issues = list(self.iter_issues(level=level, scope=scope, check_responses=check_responses))
        if error == "raise" and issues:
            raise ValueError(issues)
        if fix and issues:
            self.quiz.save()
        return issues

    def iter_issues(
        self,
        *,
        level: IssueLevelLike = IssueLevel.ALL,
        scope: QuestionScope | None = None,
        check_responses: bool = False,
        fix: bool = False,
    ) -> Iterator[Issue]:
        ref_level = IssueLevel.construct(level)

        has_scope: Callable[[Issue], bool] = lambda _: True
        if scope:
            has_scope = lambda issue: scope in issue.scopes

        for issue in self._iter_issues():
            if ref_level.accepts(issue.severity) and has_scope(issue):
                yield issue

        if scope in (None, "grading"):
            for issue in self._get_grading_issues():
                if ref_level.accepts(issue.severity) and has_scope(issue):
                    yield issue

        if scope in (None, "display"):
            for issue in self._get_display_issues():
                if ref_level.accepts(issue.severity) and has_scope(issue):
                    yield issue

        if scope in (None, "validation"):
            for issue in self._get_validation_issues():
                if ref_level.accepts(issue.severity) and has_scope(issue):
                    yield issue

    def validate_responses(
        self, /, *, save: bool = False, error: Literal["raise", "ignore"] = "raise"
    ) -> dict[StudentId, Answer]:
        """
        Validate responses and return a dictionary mapping student ids to
        validation answers.

        It always iterate over all responses collecting errors and raise
        a ValueError with a list of issues when done.

        Args:
            save:
                If True, the responses will be saved after validation.
            error:
                Determines how validation errors are handled. "raise" will raise a ValueError with a list of issues, "ignore" will ignore errors.
        """
        raise NotImplementedError("Must be implemented by subclasses.")

    def iter_response_issues(self) -> Iterator[tuple[StudentId, list[Issue]]]:
        """
        Iterate over all responses and yield a tuple of student id and a list of issues
        for each response that has issues.
        """

        for student_id, answer in self.quiz.submissions.iter_answers(question=self.id):
            try:
                self.validate_answer(answer)
            except ValueError as e:
                yield student_id, list_of_issues(e, scopes=["response"])

    #
    # Other
    #
    def convert_to(
        self,
        new_type: QuestionType,
        data: dict[str, Any] | None = None,
    ) -> Question:
        """
        Convert this question to a new type, if possible. This is used to allow
        autograders to convert questions to a different type if needed for grading.
        """
        dump = self.conf.model_dump()
        dump.update(data or {})

        match new_type:
            case "text":
                from .textual import Textual

                conf = models.Textual.model_validate(dump)
                return Textual(self.id, conf, quiz=self.quiz)
            case "repo":
                from .repo import Repo

                conf = models.Repo.model_validate(dump)
                return Repo(self.id, conf, quiz=self.quiz)
            case None:
                conf = models.GenericQuestion.model_validate(dump)
                return Generic(self.id, conf, quiz=self.quiz)
            case _:
                assert_never(new_type)

    def clear_autograder_files(self):
        """
        Clear temporary files generated by the autograder for this question.
        """
        base = self.get_root()
        for path in base.glob("tmp-*"):
            if path.is_dir():
                print(path)
                # shutil.rmtree(path, ignore_errors=True)

    #
    # Private methods designed to be overriden
    #

    def _iter_issues(self) -> Iterable[Issue]:
        """
        Get a list of issues that may prevent the question from behaving correctly in any way.

        Designed to be overridden by subclasses to provide question-specific
        issues that don't fit into the grading/display/validation categories.
        """
        return []

    def _get_grading_issues(self) -> Iterable[Issue]:
        """
        Get a list of issues that may prevent the question from being graded correctly.

        Designed to be overridden by subclasses to provide question-specific
        grading issues.
        """
        return []

    def _get_display_issues(self) -> Iterable[Issue]:
        """
        Get a list of issues that may prevent the question from being displayed
        correctly.

        Designed to be overridden by subclasses to provide question-specific
        display issues.
        """
        return []

    def _get_validation_issues(self) -> Iterable[Issue]:
        """
        Get a list of issues that may prevent the question from being validated
        correctly.

        Designed to be overridden by subclasses to provide question-specific
        validation issues.
        """
        return []


class Generic(BaseQuestion[models.GenericQuestion, AnyAnswer]):
    """
    A question with no specific assigned format.
    """

    def get_grader(self) -> Grader[Any] | None:
        return self.get_profile_grader()

    def validate_answer(self, answer: AnyAnswer) -> AnyAnswer:
        return answer


def ensure_scope(scope: QuestionScope, issues: Iterable[Issue]) -> Iterable[Issue]:
    """
    Ensure that all issues in the given list have the given scope, and if not,
    add the scope to them.
    """
    return (issue.with_scopes([scope]) for issue in issues)


def validate_type[T](value: AnyAnswer, typ: type[T], /, msg: str | None = None) -> T:
    if not isinstance(value, typ):
        if msg is None:
            msg = f"Expected type {type.__name__}, got {type(value).__name__}"
        raise type_error(msg)
    return value


def type_error(msg: str | None = None) -> ValueError:
    """
    Raise an ValueError with a type error message.
    """
    issue = Issue.error("type-error", msg, scopes=["response"])
    return ValueError(issue)


def fail(
    code: str,
    message: str,
    /,
    severity: IssueLevelLike = IssueLevel.ERROR,
    scopes: Iterable[QuestionScope] = ("response",),
) -> ValueError:
    """
    Create an issue with the given code, message, severity, and scopes.
    """
    issue = Issue(
        code=code,
        message=message,
        severity=IssueLevel.construct(severity),
        scopes=frozenset(scopes),
    )
    return ValueError(issue)


def empty_result(message: str = "Empty answer.") -> ValueError:
    """
    Create an issue for an empty answer.
    """
    return fail("empty", message, severity=IssueLevel.WARNING, scopes=["response"])


def is_empty_issue(issues: list[Issue]) -> bool:
    """
    Check if the given list of issues contains any empty answer issues.
    """
    return any(issue.code == "empty" and "response" in issue.scopes for issue in issues)


def script_priority(path: Path) -> tuple[int, str]:
    """
    Get the priority of a script based on its extension.

    The lower the number, the higher the priority.
    """
    ext = path.suffix.lower()

    if ext in {".py"}:
        return (0, ext)
    if ext in {".sh", ".bash"}:
        if sys.platform == "win32":
            return (2, ext)
        return (1, ext)
    if ext in {".bat", ".cmd"}:
        if sys.platform == "win32":
            return (1, ext)
        return (2, ext)
    if not ext:
        return (3, ext)
    return (4, ext)
