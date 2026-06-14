from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, assert_never

import rich as _rich
from pydantic import BaseModel, Field, PlainSerializer, RootModel
from rich.console import Console
from rich.syntax import Syntax

from ..data.serializers import decimal, optional
from .types import QuestionId, QuestionType

if TYPE_CHECKING:
    from ..grader import Grader
    from .assignment import Assignment

__all__ = (
    "AssociationQuestion",
    "EssayQuestion",
    "FillInQuestion",
    "GenericQuestion",
    "MultipleChoiceQuestion",
    "MultipleSelectionQuestion",
    "Question",
    "question_id",
    "validate_question",
)

type Question = Annotated[
    EssayQuestion
    | GenericQuestion
    | MultipleChoiceQuestion
    | MultipleSelectionQuestion
    | AssociationQuestion
    | FillInQuestion,
    Field(discriminator="type"),
]


class QuestionRoot(RootModel[Question]):
    root: Question


class BaseQuestion[AnswerT = Any](BaseModel):
    id: QuestionId
    type: QuestionType | None = None
    name: str | None = None
    grade: Annotated[Decimal | None, PlainSerializer(optional(decimal))] = None
    answer: AnswerT | None = None

    # Parent reference
    _assignment: Annotated[
        Assignment | None,
        Field(repr=False, exclude=True),
    ] = None

    @property
    def title(self) -> str:
        return self.name or self.id.upper()

    @property
    def base_path(self) -> Path:
        """
        Get the base path for this question, which is used to store question-specific
        files such as autograder scripts, test cases, etc.
        """
        if self._assignment is None:
            msg = "Question must be associated with an assignment to get its base path."
            raise ValueError(msg)
        return self._assignment.base_path / self.id

    def get_grader(self) -> Grader[AnswerT]:
        """
        Get the default Grader object for this question, which can be used to
        validate and grade answers to the question.
        """
        raise NotImplementedError(
            "No default grader is implemented for this question type."
        )

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
                return EssayQuestion.model_validate(
                    {**self.model_dump(), **data, "type": "text"}
                )
            case "multiple-choice":
                return MultipleChoiceQuestion.model_validate(
                    {**self.model_dump(), **data, "type": "multiple-choice"}
                )
            case "multiple-selection":
                return MultipleSelectionQuestion.model_validate(
                    {**self.model_dump(), **data, "type": "multiple-selection"}
                )
            case "association":
                return AssociationQuestion.model_validate(
                    {**self.model_dump(), **data, "type": "association"}
                )
            case "fill-in":
                return FillInQuestion.model_validate(
                    {**self.model_dump(), **data, "type": "fill-in"}
                )
            case _:
                assert_never(new_type)


class GenericQuestion(BaseQuestion):
    type: Literal[None] = None  # pyright: ignore[reportIncompatibleVariableOverride]


class EssayQuestion(BaseQuestion[str]):
    type: Literal["text"] = "text"  # pyright: ignore[reportIncompatibleVariableOverride]
    format: str | None = None

    def display_answer(self, answer: Any, rich: bool = True) -> None:
        """
        Render the question as a string.
        """
        if (
            self.format is not None
            and self.format in syntax_highlight_formats()
            and rich
        ):
            syntax = Syntax(answer, self.format, line_numbers=True, theme="monokai")
            Console().print(syntax)
        else:
            super().display_answer(answer, rich)


class MultipleChoiceQuestion(BaseQuestion[str]):
    type: Literal["multiple-choice"] = "multiple-choice"  # pyright: ignore[reportIncompatibleVariableOverride]


class MultipleSelectionQuestion(BaseQuestion[list[str]]):
    type: Literal["multiple-selection"] = "multiple-selection"  # pyright: ignore[reportIncompatibleVariableOverride]


class AssociationQuestion(BaseQuestion[dict[str, str | None]]):
    type: Literal["association"] = "association"  # pyright: ignore[reportIncompatibleVariableOverride]


class FillInQuestion(BaseQuestion[list[str]]):
    type: Literal["fill-in"] = "fill-in"  # pyright: ignore[reportIncompatibleVariableOverride]


@lru_cache(1)
def syntax_highlight_formats() -> set[str]:
    from pygments.lexers import get_all_lexers

    lexers: set[str] = set()
    for _, short_names, _, _ in get_all_lexers():
        lexers.update(short_names)
    return lexers


def validate_question(data: Any) -> Question:
    """
    Convert raw data into a validated Question object.
    """
    return QuestionRoot.model_validate(data).root


def rich_print(value: Any, *, rich: bool = True, style: str | None = None) -> None:
    """
    A wrapper around rich.print that can be used to print rich content in question answers.
    """
    if rich:
        if style is not None:
            _rich.print(f"[{style}]{value}[/{style}]")
        else:
            _rich.print(value)
    else:
        print(value)


def question_id(question: Question | QuestionId) -> QuestionId:
    return question.id if isinstance(question, BaseQuestion) else question
