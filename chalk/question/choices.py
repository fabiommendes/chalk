from __future__ import annotations

from typing import TYPE_CHECKING, Any, Collection, Iterable, Mapping

import errorz as rz
from rich.console import RenderableType
from rich.text import Text

from chalk.core import models

from ..core.answer import AnyAnswer
from ..core.issue import IssueLevel, IssueLevelLike
from ..core.models import Choice, ChoiceId, StudentId
from .base import BaseQuestion, Issue, QuestionScope

if TYPE_CHECKING:
    from ..core import Quiz

type ChoiceModel = models.MultipleChoice | models.MultipleSelection


class ChoiceQuestionBase[Conf: ChoiceModel, Answer: AnyAnswer](BaseQuestion[Conf, Answer]):
    def __init__(self, id: str, conf: Conf, *, quiz: Quiz):
        super().__init__(id, conf, quiz=quiz)
        self._choices = {c.id: c for c in conf.choices or ()}

    def _iter_issues(self) -> Iterable[Issue]:
        # Must have at least one choice
        if not self._choices:
            yield Issue.error(
                "no-choices",
                "Multiple choice question must have at least one choice.",
                scopes=["grading", "validation"],
            )

    def get_choice(self, choice_id: ChoiceId) -> Choice | None:
        return self._choices.get(choice_id)

    def validate_question_with_responses(
        self,
        responses: Mapping[StudentId, Response],
        *,
        level: IssueLevelLike = IssueLevel.ALL,
        scope: QuestionScope | None = None,
    ) -> rz.Result[OK, list[Issue]]:
        issues: list[Issue] = []

        # Infer choices, if not defined
        if not self._choices:
            self._choices, issues = self._infer_choices_from_responses(responses)
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
        ) -> tuple[dict[ChoiceId, Choice], list[Issue]]: ...

        def validate_question(
            self,
            *,
            level: IssueLevelLike = IssueLevel.ALL,
            scope: QuestionScope | None = None,
        ) -> None: ...


def display_choices(choices: Collection[Choice], plain: bool = False) -> Iterable[RenderableType]:
    if not choices:
        yield Text("No choices provided", style="italic")
    for choice in choices:
        yield Text.assemble(f"  - {choice.title} ", (f"id: {choice.id}", "dim"))


def validate_choice_id(value: Any) -> ChoiceId:
    """
    Validate that the given value is a valid ChoiceId (string).
    """
    if isinstance(value, Mapping) and "id" in value:
        value = value["id"]

    if not isinstance(value, str):
        raise ValueError(f"Choice ID must be a string, got {type(value).__name__}")
    return value


def validate_choice_ids(value: Any) -> list[ChoiceId]:
    """
    Validate that the given value is a list of valid ChoiceIds (strings).
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [validate_choice_id(v) for v in value]
    raise ValueError(f"Choice IDs must be a list of strings, got {type(value).__name__}")
