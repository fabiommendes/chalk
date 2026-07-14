from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING, Iterable, Iterator, Mapping, TypeIs, cast

import errorz as rz
import opt
from rich.console import RenderableType
from rich.text import Text

from ..core import disqualification as dis
from ..core import models
from ..core.answer import AnyAnswer, AssociationAnswer
from ..core.grader import Graded
from ..core.issue import IssueLevel, IssueLevelLike
from ..core.models import (
    AssociationChoice,
    AssociationResponse,
    ChoiceId,
    QuestionId,
    ResponseId,
    StudentId,
)
from .base import (
    BaseQuestion,
    Issue,
    QuestionScope,
    fail,
    type_error,
)
from .renderable import RenderableField

if TYPE_CHECKING:
    from ..core import Quiz


class Association(BaseQuestion[models.Association, AssociationAnswer]):
    @property
    def grading_method(self) -> str:
        return self._conf.grading_method or "partial"

    def __init__(self, id: QuestionId, conf: models.Association, *, quiz: Quiz):
        super().__init__(id, conf, quiz=quiz)
        self._choices = {c.id: c for c in conf.choices or ()}
        self._responses = {r.id: r for r in conf.responses or ()}

    #
    # Getters
    #
    def get_choice(self, id: ChoiceId) -> AssociationChoice | None:
        return self._choices.get(id)

    def get_response(self, id: ResponseId) -> AssociationResponse | None:
        return self._responses.get(id)

    def _render_base_fields(self, plain: bool = False) -> Iterable[tuple[str, RenderableField]]:
        yield from super()._render_base_fields(plain)
        yield "grading_method", self.grading_method

    def _render_base_sections(self, plain: bool = False) -> Iterable[RenderableType]:
        yield from super()._render_base_sections(plain)

        if self._choices:
            yield Text("Choices:", style="bold underline")
            for x in self._choices.values():
                yield Text.assemble(f"  - {x.title}", (f"(id: {x.id})", "dim"))
        if self._responses:
            yield Text("Responses:", style="bold underline")
            for y in self._responses.values():
                yield Text.assemble(f"  - {y.title}", (f"(id: {y.id})", "dim"))

    #
    # Validation
    #
    def validate_answer(self, value: AnyAnswer) -> AssociationAnswer:
        if not isinstance(value, dict):
            raise type_error(f"Expected a dict[str, str], got {type(value).__name__}.")

        # All key/values in the dict are have valid types
        for k, v in value.items():
            if not isinstance(k, str):
                msg = f"Expected a dict[str, str], got a key of type {type(k).__name__}."
                raise type_error(msg)
            if v is not None and not isinstance(v, str | None):
                msg = f"Expected a dict[str, str], got a value of type {type(v).__name__}."
                raise type_error(msg)

        val = cast(AssociationAnswer, value)

        # All keys are in the choices
        choice_ids = set(self._choices)
        invalid_keys = set(val.keys()) - choice_ids
        if invalid_keys:
            invalid_repr = ", ".join(invalid_keys)
            raise fail(
                "invalid-association",
                f"Selected choice does not exist: {invalid_repr!r}.",
                scopes=["response"],
            )

        # All values are in the responses
        response_ids = set(self._responses)
        invalid_values = {v for v in val.values() if v is not None} - response_ids
        if invalid_values:
            invalid_repr = ", ".join(invalid_values)
            raise fail(
                "invalid-association",
                f"Selected response does not exist: {invalid_repr!r}.",
                scopes=["response"],
            )

        return val

    def iter_issues(
        self,
        *,
        level: IssueLevelLike = IssueLevel.ALL,
        scope: QuestionScope | None = None,
        check_responses: bool = False,
        fix: bool = False,
    ) -> Iterator[Issue]:
        yield from super().iter_issues(
            level=level, scope=scope, check_responses=check_responses, fix=fix
        )
        yield from self._find_inconsistent_grades()

    def grade_answer(self, answer: AssociationAnswer) -> Graded | None:
        partial = Decimal(0)
        default_grade = Decimal(1) / max(len(self._choices), 1)

        for id, response in answer.items():
            choice = self.get_choice(id)
            if choice is None:
                return Graded(dis.InvalidInput())
            if response is not None and response == choice.response:
                partial += opt.unwrap(choice.value, default_grade)
            elif self.grading_method == "all-or-nothing":
                return Graded.null_score()

        grade = opt.unwrap(self.value, Decimal(1))
        return Graded(partial * grade)

    #
    # Utility methods
    #
    def validate_question_with_responses(
        self,
        responses: Mapping[StudentId, models.Response],
        *,
        level: IssueLevelLike = IssueLevel.ALL,
        scope: QuestionScope | None = None,
    ) -> rz.Result[OK, list[Issue]]:
        issues: list[Issue] = []

        # Infer choices, if not defined
        infered = False
        if not self._responses or not self._choices:
            self._choices, self._responses, issues = self._infer_mapping_from_responses(responses)
            infered = True

        if infered:
            issues.append(
                Issue.warning(
                    "inferred-choices",
                    "No choices in the responses and choices were defined, so they were inferred from responses.",
                    scopes=["validation"],
                )
            )

        if not (res := self.validate_question(level=level, scope=scope)):
            issues.extend(res.error)
        return rz.err(issues) if issues else ok

    def _infer_mapping_from_responses(
        self, responses_data: Mapping[StudentId, models.Response]
    ) -> tuple[
        dict[ChoiceId, AssociationChoice],
        dict[ResponseId, AssociationResponse],
        list[Issue],
    ]:

        choice_ids = set[str]()
        response_ids = set[str]()

        for response in responses_data.values():
            if isinstance(response.answer, dict):
                for choice_id, response_id in response.answer.items():
                    if isinstance(choice_id, str):
                        choice_ids.add(choice_id)
                    if isinstance(response_id, str):
                        response_ids.add(response_id)

        grade = Decimal(1) / max(len(choice_ids), 1)
        choices = self._choices
        if not choices:
            choices = {id: AssociationChoice(id=id, value=grade) for id in sorted(choice_ids)}

        responses = self._responses
        if not responses:
            responses = {id: AssociationResponse(id=id) for id in sorted(response_ids)}

        issues: list[Issue] = []
        return choices, responses, issues

    def _find_inconsistent_grades(self) -> Iterator[Issue]:
        """
        Check for inconsistent grading issues in the given responses.
        """
        grades: dict[tuple[tuple[str, str], ...], set[Decimal]] = defaultdict(set)
        students: dict[tuple[tuple[str, str], ...], set[StudentId]] = defaultdict(set)

        # TODO
        raise NotImplementedError
        # for student_id, response in responses.items():
        #     match opt.map(self.validate_answer, response.answer):
        #         case None:
        #             continue
        #         case rz.Err(_):
        #             continue
        #         case ans:
        #             if response.grade is None:
        #                 continue
        #             answer_key = as_key(ans)
        #             grades[answer_key].add(response.grade.non_adjusted)
        #             students[answer_key].add(student_id)

        # issues: dict[StudentId, Issue] = {}
        # for answer, grade_set in grades.items():
        #     if len(grade_set) <= 1:
        #         continue
        #     for student_id in students[answer]:
        #         issues[student_id] = Issue.warning(
        #             "inconsistent-grades",
        #             f"Inconsistent grades for answer {answer!r}.",
        #             scopes=["grading"],
        #         )

        # return issues

    def _get_grading_issues(self) -> Iterable[Issue]:
        # Must have at least one choice with the maximum grade.
        grades = [choice.value for choice in self._choices.values() if choice.value is not None]
        total = sum(grades, Decimal())
        if total < 0.99:
            yield Issue.error(
                "no-correct-choice",
                f"Association cannot achieve full credit. Choices add up to {total}.",
                scopes=["grading"],
            )
        elif total > 1.01:
            yield Issue.error(
                "no-correct-choice",
                f"Association can achieve more than full credit. Choices add up to {total}.",
                scopes=["grading"],
            )

        # Check if answer key is defined
        if not self._conf.answer_key:
            yield Issue.warning(
                "no-answer-key",
                "No answer key is defined for this association question. Impossible to grade automatically.",
                scopes=["grading"],
            )


def is_dict_of[K, V](
    data: dict[K, V | None], /, key: type[K], value: type[V]
) -> TypeIs[dict[K, V | None]]:
    for k, v in data.items():
        if not isinstance(k, key):
            return False
        if v is None:
            continue
        if not isinstance(v, value):
            return False
    return True


def as_key(data: AssociationAnswer, /) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((k, v) for k, v in data.items() if v is not None))
