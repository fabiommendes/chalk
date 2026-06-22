from decimal import Decimal
from typing import Annotated, Any, Literal, Mapping, assert_never

import errorz as rz
from pydantic import Field

from ..core.grader import Graded
from ..core.submission import Response
from ..types import Answer, StudentId
from ..util.show import display_field
from .base import (
    BaseQuestion,
    Issue,
    fail,
)
from .choices import (
    Choice,
    ChoiceAnswer,
    ChoiceId,
    HasChoicesMixin,
    choice_answer_id,
    display_choices,
    try_choice_answer_ids,
)

zero = Decimal(0)
one = Decimal(1)


class MultipleSelection(HasChoicesMixin, BaseQuestion[list[ChoiceAnswer]]):
    """
    A question in which students mark multiple answers from a list of options.

    The answer is a list of ids of the selected choices. The grade is determined
    by the grades associated with the selected choices using the sum, mean, product,
    or min aggregation method.
    """

    type: Literal["multiple-selection"] = "multiple-selection"  # pyright: ignore[reportIncompatibleVariableOverride]
    grading_method: Literal["sum", "all-or-nothing", "min", "mean"] = "sum"
    choices: Annotated[list[Choice], Field(default_factory=list)]

    def validate_answer(self, answer: Answer) -> rz.Result[Any, list[Issue]]:
        choice_ids = try_choice_answer_ids(answer)
        if choice_ids is None:
            return fail(
                "invalid-type",
                "Answer must be a list of choices.",
                scopes=["response"],
            )

        # Prevent duplicate choices
        choice_set = set(choice_ids)
        if len(choice_set) != len(choice_ids):
            return fail(
                "duplicate-choices",
                "Answer contains duplicate choices.",
                scopes=["response"],
            )

        valid_choices = {choice.id for choice in self.choices}
        invalid = choice_set - valid_choices
        if invalid:
            invalid_repr = ", ".join(invalid)
            return fail(
                "invalid-choice",
                f"Selected choice does not exist: {invalid_repr!r}.",
                scopes=["response"],
            )
        return choice_ids

    def grade_answer(self, answer: list[ChoiceAnswer]) -> Graded | None:
        answer_set = {choice_answer_id(a) for a in answer}
        grades = set()
        for choice in self.choices:
            if choice.id in answer_set:
                grades.add(choice.grade or zero)

        # Compute the grade
        total: Decimal
        match self.grading_method:
            case "sum":
                total = sum(grades, zero)
            case "mean":
                total = zero
                if grades:
                    total = sum(grades, zero) / len(grades)
            case "min":
                total = min(grades, default=zero)
            case "all-or-nothing":
                expected = {
                    choice.id
                    for choice in self.choices
                    if choice.grade and choice.grade > 0
                }
                total = one if answer_set == expected else zero
            case other:
                assert_never(other)

        return Graded(total * (self.grade or one))

    def display(self, rich: bool = True) -> None:
        super().display(rich=rich)
        display_field("grading method", self.grading_method, rich=rich)
        display_choices(self.choices, rich=rich)

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
        for response in responses.values():
            answer = try_choice_answer_ids(response.answer)
            if answer is not None:
                choice_ids.update(answer)

        return [Choice(id=id) for id in choice_ids], []
