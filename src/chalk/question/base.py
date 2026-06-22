from __future__ import annotations

from abc import abstractmethod
from decimal import Decimal
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Iterable,
    Literal,
    Mapping,
    assert_never,
    cast,
)

import errorz as rz
from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer

from ..core.grader import Graded, Grader
from ..core.issue import Issue as _issue
from ..core.issue import IssueLevel, IssueLevelLike
from ..core.submission import Response
from ..data import serializers as s
from ..data import validators as v
from ..types import Answer, QuestionId, QuestionType, StudentId
from ..util.show import display_field, rich_print

if TYPE_CHECKING:
    from ..core.assignment import Assignment
    from ..question import (
        Association,
        FillIn,
        MultipleChoice,
        MultipleSelection,
        Question,
        Textual,
    )


type QuestionScope = Literal["grading", "display", "validation", "response"]
Issue = _issue[str, QuestionScope]
type OK = Literal[True]
ok: OK = True
zero = Decimal(0)
one = Decimal(1)
issue: type[_issue] = _issue


class BaseQuestion[AnswerT = Any](BaseModel):
    id: QuestionId
    type: QuestionType | None = None
    name: str | None = None
    grade: Annotated[
        Decimal | None,
        PlainSerializer(s.optional(s.decimal)),
        BeforeValidator(v.optional(v.decimal)),
    ] = None
    answer_key: AnswerT | None = None

    # Parent reference
    _assignment: Annotated[
        Assignment | None,
        Field(repr=False, exclude=True),
    ] = None

    @property
    def title(self) -> str:
        """
        A human readable display for the question. Uses name or id, whichever is available.
        """
        return self.name or self.id.upper()

    def get_assignment(self) -> Assignment | None:
        return self._assignment

    def get_root_path(self, mkdir: bool = False) -> Path:
        """
        Get the base path for this question, which is used to store question-specific
        files such as autograder scripts, test cases, etc.
        """
        if self._assignment is None:
            msg = "Question must be associated with an assignment to get its base path."
            raise ValueError(msg)
        base_path = self._assignment.base_path / self.id

        if base_path.exists() and not base_path.is_dir():
            msg = f"Path is not a directory: {base_path}"
            raise RuntimeError(msg)

        if mkdir:
            base_path.mkdir(parents=True, exist_ok=True)
        return base_path

    def get_responses(self) -> Mapping[StudentId, Response]:
        """
        Get a mapping of student ids to responses.

        Requires the question to be associated with an assignment, otherise returns an empty mapping.
        """
        assignment = self.get_assignment()
        if assignment is None:
            return {}
        return assignment.get_responses_for_question(self.id)

    def validate_question(
        self,
        *,
        level: IssueLevelLike = IssueLevel.ALL,
        scope: QuestionScope | None = None,
    ) -> rz.Result[OK, list[Issue]]:
        """
        Get a list of issues with the question that may prevent it from behaving
        correctly.

        This can be used to provide feedback to instructors when they create
        or edit questions.

        Observations:
            Implementers of subclasses may prefer to override any of the specialized
            methods
                _get_issues() - issues of any type
                _get_grading_issues() - only grading issues
                _get_display_issues() - only display issues
                _get_validation_issues() - only validation issues
        """
        issues: list[Issue] = list(self._get_issues())
        if scope is not None:
            issues = [issue for issue in issues if scope in issue.scopes]
        if scope in (None, "grading"):
            issues.extend(ensure_scope("grading", self._get_grading_issues()))
        if scope in (None, "display"):
            issues.extend(ensure_scope("display", self._get_display_issues()))
        if scope in (None, "validation"):
            issues.extend(ensure_scope("validation", self._get_validation_issues()))

        level = IssueLevel.construct(level)
        errors = [issue for issue in issues if issue.severity & level]
        return rz.err(errors) if errors else ok

    def validate_question_with_responses(
        self,
        responses: Mapping[StudentId, Response],
        *,
        level: IssueLevelLike = IssueLevel.ALL,
        scope: QuestionScope | None = None,
    ) -> rz.Result[OK, list[Issue]]:
        """
        Allow pass information from responses to cross-validate the question
        and the responses together.

        The default implementation simply calls validate_question and ignore
        the responses.
        """
        return self.validate_question(level=level, scope=scope)

    @abstractmethod
    def validate_answer(self, answer: Answer, /) -> rz.Result[AnswerT, list[Issue]]:
        """
        Validate a student answer and return a list of issues
        with the answer that may prevent it from being graded correctly.

        """
        raise NotImplementedError("Must be implemented by subclasses.")

    def validate_responses(
        self, responses: Mapping[StudentId, Response], /, *, inplace: bool = False
    ) -> dict[StudentId, rz.Result[Response, list[Issue]]]:
        """
        Validate a set of responses and return a dictionary mapping student ids to
        validation results.

        May allow for validation that depends on multiple responses (e.g. for plagiarism detection).

        Args:
            responses:
                A mapping of student ids to responses.
            inplace:
                If True, the responses will be modified *in place*.
        """
        results: dict[StudentId, rz.Result[Response, list[Issue]]] = {}
        for student_id, response in responses.items():
            raw_answer = response.answer
            if raw_answer is None:
                continue

            answer: AnswerT | None = None
            result = self.validate_answer(raw_answer)
            if rz.is_err(result) and is_empty_issue(result.error):
                answer = None
            elif rz.is_err(result):
                results[student_id] = result
                continue
            else:
                answer = result

            if inplace:
                response.answer = cast(Answer, answer)
            else:
                response = response.model_copy(update={"answer": answer})

            results[student_id] = response
        return results

    def get_grader(self) -> rz.Result[Grader[AnswerT], str]:
        """
        Get the default Grader object for this question, which can be used to
        validate and grade answers to the question.

        If the question do not support automatic grading, return an error
        with an appropriate message.
        """
        if not hasattr(self, "grade_answer"):
            return rz.err("This question type does not support automatic grading.")

        def grader(id: StudentId, answer: AnswerT, /, **kwargs: Any) -> Graded | None:
            return self.grade_answer(answer)  # type: ignore

        return grader

    def display(self, rich: bool = True) -> None:
        """
        Display the question in the console.
        """

        # Print title
        if self.name and self.name != self.id:
            rich_print(f"[bold underline]{self.name} [dim]({self.id})[/]", rich=rich)
        else:
            rich_print(f"[bold underline]{self.title}[/]", rich=rich)

        # Print basic info
        display_field("type", self.type, rich=rich)
        display_field("grade", self.grade, rich=rich)

    def display_answer(self, answer: Any, rich: bool = True) -> None:
        """
        Display the answer to the question in the console.
        """
        if answer is None and rich:
            rich_print("No answer provided.", rich=rich, style="italic")
        else:
            rich_print(answer, rich=rich)

    def convert_to(
        self,
        new_type: QuestionType,
        data: dict[str, Any] | None = None,
    ) -> Question:
        """
        Convert this question to a new type, if possible. This is used to allow
        autograders to convert questions to a different type if needed for grading.
        """
        data = data or {}
        match new_type:
            case "text":
                return Textual.model_validate(
                    {**self.model_dump(), **data, "type": "text"}
                )
            case "multiple-choice":
                return MultipleChoice.model_validate(
                    {**self.model_dump(), **data, "type": "multiple-choice"}
                )
            case "multiple-selection":
                return MultipleSelection.model_validate(
                    {**self.model_dump(), **data, "type": "multiple-selection"}
                )
            case "association":
                return Association.model_validate(
                    {**self.model_dump(), **data, "type": "association"}
                )
            case "fill-in":
                return FillIn.model_validate(
                    {**self.model_dump(), **data, "type": "fill-in"}
                )
            case _:
                assert_never(new_type)

    #
    # Private methods
    #
    def _get_issues(self) -> Iterable[Issue]:
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


class Generic(BaseQuestion):
    """
    A question with no specific assigned format.
    """

    type: Literal[None] = None  # pyright: ignore[reportIncompatibleVariableOverride]

    def get_grader(self) -> rz.Result[Grader[Any], str]:
        return rz.err("Generic questions do not support automatic grading.")

    def validate_answer(self, answer: Answer) -> rz.Result[Any, list[Issue]]:
        return rz.ok(answer)


def ensure_scope(scope: QuestionScope, issues: Iterable[Issue]) -> Iterable[Issue]:
    """
    Ensure that all issues in the given list have the given scope, and if not,
    add the scope to them.
    """
    return (issue.with_scopes([scope]) for issue in issues)


def validate_type[T](
    value: Answer, typ: type[T], /, msg: str | None = None
) -> rz.Result[T, list[Issue]]:
    if not isinstance(value, typ):
        if msg is None:
            msg = f"Expected type {type.__name__}, got {type(value).__name__}"
        return rz.err(
            [
                Issue.error(
                    "type-error",
                    (msg or "Invalid type") + f", got {type(value).__name__}",
                    scopes=["response"],
                )
            ]
        )
    return rz.ok(value)


def fail(
    code: str,
    message: str,
    severity: IssueLevelLike = IssueLevel.ERROR,
    scopes: Iterable[QuestionScope] = ("response",),
) -> rz.Result[Any, list[Issue]]:
    """
    Create an issue with the given code, message, severity, and scopes.
    """
    return rz.err(
        [
            _issue(
                code=code,
                message=message,
                severity=IssueLevel.construct(severity),
                scopes=frozenset(scopes),
            )
        ]
    )


def empty_issue(message: str = "Empty answer.") -> rz.Result[Any, list[Issue]]:
    """
    Create an issue for an empty answer.
    """
    return fail("empty", message, severity=IssueLevel.WARNING, scopes=["response"])


def is_empty_issue(issues: list[Issue]) -> bool:
    """
    Check if the given list of issues contains any empty answer issues.
    """
    return any(issue.code == "empty" and "response" in issue.scopes for issue in issues)
