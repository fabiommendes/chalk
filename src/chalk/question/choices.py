from decimal import Decimal
from typing import TYPE_CHECKING, Annotated, Iterable, Mapping, NotRequired, TypedDict

import errorz as rz
from pydantic import BaseModel, BeforeValidator, PlainSerializer

from ..core.issue import IssueLevel, IssueLevelLike
from ..core.submission import Response
from ..data import serializers as s
from ..data import validators as v
from ..types import Answer, StudentId
from ..util.show import rich_print
from .base import OK, Issue, QuestionScope, ok

type ChoiceId = str
type ChoiceAnswer = ChoiceId | ChoiceAnswerDict


class Choice(BaseModel):
    id: ChoiceId
    text: str | None = None
    grade: Annotated[
        Decimal | None,
        PlainSerializer(s.optional(s.decimal)),
        BeforeValidator(v.optional(v.decimal)),
    ] = None

    @property
    def title(self) -> str:
        return self.text or self.id


class HasChoicesMixin:
    choices: list[Choice]

    def _get_issues(self) -> Iterable[Issue]:
        # Must have at least one choice
        if not self.choices:
            yield Issue.error(
                "no-choices",
                "Multiple choice question must have at least one choice.",
                scopes=["grading", "validation"],
            )

    def get_choice(self, choice_id: ChoiceId) -> Choice | None:
        for choice in self.choices:
            if choice.id == choice_id:
                return choice
        return None

    def _validate_question_with_responses(
        self,
        responses: Mapping[StudentId, Response],
        *,
        level: IssueLevelLike = IssueLevel.ALL,
        scope: QuestionScope | None = None,
    ) -> rz.Result[OK, list[Issue]]:
        issues: list[Issue] = []

        # Infer choices, if not defined
        if not self.choices:
            self.choices, issues = self._infer_choices_from_responses(responses)
            issues.append(
                Issue.warning(
                    "inferred-choices",
                    "No choices were defined, so they were inferred from responses.",
                    scopes=["validation"],
                )
            )

        if not (res := self.validate_question(level=level, scope=scope)):
            issues.extend(res.error)
        return rz.err(issues) if issues else ok

    if TYPE_CHECKING:

        def _infer_choices_from_responses(
            self, responses: Mapping[StudentId, Response]
        ) -> tuple[list[Choice], list[Issue]]: ...

        def validate_question(
            self,
            *,
            level: IssueLevelLike = IssueLevel.ALL,
            scope: QuestionScope | None = None,
        ) -> rz.Result[OK, list[Issue]]: ...


def choice_answer_id(answer: ChoiceAnswer, /) -> ChoiceId:
    return answer if isinstance(answer, str) else answer["id"]


def try_choice_answer_id(answer: Answer | None, /) -> ChoiceId | None:
    if answer is None or isinstance(answer, str):
        return answer
    if (
        isinstance(answer, dict)
        and {"id", "text"}.issuperset(answer.keys())
        and "id" in answer
    ):
        return answer["id"]
    return None


def try_choice_answer_ids(answer: Answer | None, /) -> list[ChoiceId] | None:
    if answer is None:
        return answer

    items: list[ChoiceId] = []
    if isinstance(answer, list):
        for x in answer:
            if (id := try_choice_answer_id(x)) is None:
                return None
            items.append(id)
        return items
    return None


class ChoiceAnswerDict(TypedDict):
    id: ChoiceId
    text: NotRequired[str]


def display_choices(choices: list[Choice], rich: bool = True) -> None:
    if not choices:
        rich_print("No choices provided.", rich=rich, style="italic")
    for choice in choices:
        rich_print(f"  - {choice.title} [dim](id: {choice.id})[/]", rich=rich)
