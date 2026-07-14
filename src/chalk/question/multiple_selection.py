from decimal import Decimal
from typing import Iterable, Literal, Mapping, assert_never

from rich.console import RenderableType

from ..core import models
from ..core.answer import AnyAnswer, MultipleSelectionAnswer
from ..core.grader import Graded
from ..core.models import (
    Choice,
    ChoiceId,
    Response,
    StudentId,
)
from .base import (
    Issue,
    fail,
)
from .choices import (
    ChoiceQuestionBase,
    display_choices,
    validate_choice_ids,
)
from .renderable import RenderableField


class MultipleSelection(ChoiceQuestionBase[models.MultipleSelection, MultipleSelectionAnswer]):
    """
    A question in which students mark multiple answers from a list of options.

    The answer is a list of ids of the selected choices. The grade is determined
    by the grades associated with the selected choices using the sum, mean, product,
    or min aggregation method.
    """

    @property
    def grading_method(self) -> Literal["sum", "all-or-nothing", "min", "mean"]:
        return self._conf.grading_method

    def validate_answer(self, answer: AnyAnswer | str) -> MultipleSelectionAnswer:
        if isinstance(answer, str):
            answer = [a.strip() for a in answer.split(";")]

        choice_ids = validate_choice_ids(answer)

        # Prevent duplicate choices
        choice_set = set(choice_ids)
        if len(choice_set) != len(choice_ids):
            raise fail(
                "duplicate-choices",
                "Answer contains duplicate choices.",
                scopes=["response"],
            )

        invalid = choice_set - set(self._choices)
        if invalid:
            invalid_repr = ", ".join(invalid)
            raise fail(
                "invalid-choice",
                f"Selected choice does not exist: {invalid_repr!r}.",
                scopes=["response"],
            )
        return choice_ids

    def grade_answer(self, answer: MultipleSelectionAnswer) -> Graded | None:
        answer_set = set(answer)
        grades = []
        for id in answer_set & self._choices.keys():
            choice = self._choices[id]
            grades.append(choice.value)

        # Compute the grade
        total: Decimal
        match self.grading_method:
            case "sum":
                total = sum(grades, Decimal(0))
            case "mean":
                total = Decimal(0)
                if grades:
                    total = sum(grades, Decimal(0)) / len(grades)
            case "min":
                total = min(grades, default=Decimal(0))
            case "all-or-nothing":
                expected = {id for id, choice in self._choices.items() if choice.value > 0}
                total = Decimal(1) if answer_set == expected else Decimal(0)
            case other:
                assert_never(other)

        return Graded(total)

    def _render_base_fields(self, plain: bool = False) -> Iterable[tuple[str, RenderableField]]:
        yield from super()._render_base_fields(plain)
        yield "grading method", self.grading_method

    def _render_base_sections(self, plain: bool = False) -> Iterable[RenderableType]:
        yield from super()._render_base_sections(plain)
        yield from display_choices(self._choices.values(), plain=plain)

    #
    # Utility methods
    #
    def _infer_choices_from_responses(
        self, responses: Mapping[StudentId, Response]
    ) -> tuple[list[Choice], list[Issue]]:
        """
        Infer the choices for this question from the given responses.

        This is used to provide feedback to instructors when they create or edit questions without explicitly providing choices, but there are already responses with answers that can be used to infer the choices.
        """
        choice_ids: set[ChoiceId] = set()
        grades = dict[tuple[str, ...], Decimal]()

        for response in responses.values():
            try:
                answer = self.validate_answer(response.answer)
            except ValueError:
                continue

            choice_ids.update(answer)
            if response.grade is not None:
                key = tuple(sorted(answer))
                grades[key] = response.grade.value

        if not choice_ids:
            return [], [inference_issue("No valid responses to infer choices from.")]

        match self.grading_method:
            case "sum":
                return infer_choices_for_sum(
                    choice_ids,
                    grades,
                    self.grade or one,
                )
            case "mean":
                return infer_choices_for_mean(
                    choice_ids,
                    grades,
                    max_grade=self.grade or one,
                )
            case "min":
                return infer_choices_for_min(
                    choice_ids,
                    grades,
                    max_grade=self.grade or one,
                )
            case "all-or-nothing":
                return infer_choices_for_all_or_nothing(
                    choice_ids,
                    grades,
                    max_grade=self.grade or one,
                )
            case other:
                assert_never(other)


def infer_choices_for_sum(
    ids: set[ChoiceId],
    grades: dict[tuple[str, ...], Decimal],
    max_grade: Decimal,
) -> tuple[list[Choice], list[Issue]]:
    grades = grades.copy()
    known_values: dict[ChoiceId, Choice] = {}

    while grades:
        size = len(grades)

        # Extract all answers that have a single choice and a known grade
        for key, grade in list(grades.items()):
            if len(key) == 1:
                choice_id = key[0]
                if choice_id in known_values:
                    continue
                known_values[choice_id] = Choice(id=choice_id, grade=grade)
                del grades[key]

        # Remove all known values from the remaining grades
        for key in list(grades.keys()):
            common = set(key).intersection(known_values.keys())
            if not common:
                continue

            new_key = tuple(sorted(set(key) - common))
            new_grade = grades[key] - sum(known_values[c].grade or zero for c in common)
            del grades[key]
            grades[new_key] = new_grade

        if len(grades) == size:
            # No progress was made, we cannot infer any more choices
            break
    else:
        # All grades have been resolved, return the known values
        return list(known_values.values()), []

    if max_grade in grades.values():
        return infer_choices_for_all_or_nothing(ids, grades, max_grade)

    known_values.update({id: Choice(id=id) for id in ids if id not in known_values})
    msg = "Could not infer all choice grades from the given responses. Some choices may be missing or have conflicting grades."
    return list(known_values.values()), [inference_issue(msg)]


def infer_choices_for_mean(
    ids: set[ChoiceId],
    grades: dict[tuple[str, ...], Decimal],
    max_grade: Decimal,
) -> tuple[list[Choice], list[Issue]]:
    # TODO: implement this discovery algorith
    return plain_choices(ids), []


def infer_choices_for_min(
    ids: set[ChoiceId],
    grades: dict[tuple[str, ...], Decimal],
    max_grade: Decimal,
) -> tuple[list[Choice], list[Issue]]:
    # TODO: implement this discovery algorith
    return plain_choices(ids), []


def infer_choices_for_all_or_nothing(
    ids: set[ChoiceId],
    grades: dict[tuple[str, ...], Decimal],
    max_grade: Decimal,
) -> tuple[list[Choice], list[Issue]]:
    grade = max_grade / len(ids) if ids else one
    for key, grade in grades.items():
        if grade == max_grade:
            return [Choice(id=id, grade=grade if id in key else zero) for id in key], []

    msg = "No answer achieved the maximum grade. Could not determine the answer-key."
    return plain_choices(ids), [inference_issue(msg)]


def plain_choices(choice_ids: set[ChoiceId]) -> list[Choice]:
    return [Choice(id=id) for id in choice_ids]
