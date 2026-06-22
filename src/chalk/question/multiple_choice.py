import operator
from collections import defaultdict
from decimal import Decimal
from typing import Annotated, Iterable, Literal, Mapping

import errorz as rz
import opt
from pydantic import Field

from ..core import disqualification as dis
from ..core.grade import Grade
from ..core.grader import Graded
from ..core.submission import Response
from ..types import Answer, StudentId
from ..util.show import display_field
from .base import (
    BaseQuestion,
    Issue,
    empty_issue,
    fail,
    validate_type,
)
from .choices import (
    Choice,
    ChoiceAnswer,
    HasChoicesMixin,
    choice_answer_id,
    display_choices,
    try_choice_answer_id,
)
from .util import merge_errors

zero = Decimal(0)
one = Decimal(1)


class MultipleChoice(HasChoicesMixin, BaseQuestion[ChoiceAnswer]):
    """
    A question in which students mark a single answer from a list of options.

    The answer is the id of the selected choice. The grade is determined by the
    grade associated with the selected choice.
    """

    type: Literal["multiple-choice"] = "multiple-choice"  # pyright: ignore[reportIncompatibleVariableOverride]
    penalty: Literal["fair", "negative", "half", "third"] | Decimal | None = None
    choices: Annotated[list[Choice], Field(default_factory=list)]

    def _get_grading_issues(self) -> Iterable[Issue]:
        # Must have at least one choice with the maximum grade.
        grades = [choice.grade for choice in self.choices if choice.grade is not None]
        if max(grades, default=0) < 1:
            yield Issue.error(
                "no-correct-choice",
                "Multiple choice question has no correct choice.",
                scopes=["grading"],
            )

    def validate_answer(self, answer: Answer) -> rz.Result[str, list[Issue]]:
        if rz.is_err(val := validate_type(answer, str)):
            return val
        if not val:
            return empty_issue()
        if not any(val == choice.id for choice in self.choices):
            return fail(
                "invalid-choice",
                f"Selected choice does not exist: {val!r}.",
                scopes=["response"],
            )
        return val

    def validate_responses(
        self,
        responses: Mapping[StudentId, Response],
        /,
        *,
        inplace: bool = False,
    ) -> dict[StudentId, rz.Result[Response, list[Issue]]]:
        result = super().validate_responses(responses, inplace=inplace)
        inconsistent_grades = self._find_inconsistent_grades(responses)
        return merge_errors(
            operator.add,
            result,
            {k: rz.err([v]) for k, v in inconsistent_grades.items()},
        )

    def display(self, rich: bool = True) -> None:
        super().display(rich=rich)
        display_field("penalty", self.penalty, rich=rich)
        display_choices(self.choices, rich=rich)

    #
    # Grading methods
    #

    def grade_answer(self, answer: ChoiceAnswer) -> Graded | None:
        """
        Grade the given answer and return the grade as a decimal between 0 and 1.

        This is a helper method that can be used by graders for this question type.
        """
        id = choice_answer_id(answer)
        choice = self.get_choice(id)

        # Disqualify missing choices
        if choice is None:
            return Graded(Grade(0, disqualify=dis.Invalid()))

        weight = self.grade or one
        grade = choice.grade or zero

        return Graded(grade * weight)

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
        choice_grades: dict[str, set[Decimal | None]] = defaultdict(set)
        for response in responses.values():
            answer = try_choice_answer_id(response.answer)
            if answer is not None and answer != "":
                choice_grades[answer].add(opt.getattr(response.grade, "non_adjusted"))

        # Rebuild choice ids
        issues: list[Issue] = []
        choices: list[Choice] = []
        for choice_id, grades in choice_grades.items():
            match [x for x in grades if x is not None]:
                case [] | [None]:
                    grade = None
                case [single]:
                    grade = single
                    if grade:
                        grade /= opt.unwrap(self.grade, one)
                case _:
                    grade = None
                    issues.append(
                        Issue.warning(
                            "inconsistent-grades",
                            f"Inconsistent grades for choice {choice_id!r}.",
                            scopes=["grading"],
                        )
                    )
            choices.append(Choice(id=choice_id, grade=grade))
        return choices, issues

    def _find_inconsistent_grades(
        self, responses: Mapping[StudentId, Response]
    ) -> dict[StudentId, Issue]:
        """
        Check for inconsistent grading issues in the given responses.

        For example, if a student selected a choice that should receive full credit but received a zero, that would be an inconsistency.
        """
        grades: dict[str, set[Decimal]] = defaultdict(set)
        students: dict[str, set[StudentId]] = defaultdict(set)

        for student_id, response in responses.items():
            answer = try_choice_answer_id(response.answer)
            if answer is None:
                continue

            # Now answer is validated as str
            if response.grade is None:
                continue
            grades[answer].add(response.grade.non_adjusted)
            students[answer].add(student_id)

        issues: dict[StudentId, Issue] = {}
        for answer, grade_set in grades.items():
            if len(grade_set) <= 1:
                continue
            for student_id in students[answer]:
                issues[student_id] = Issue.warning(
                    "inconsistent-grades",
                    f"Inconsistent grades for answer {answer!r}.",
                    scopes=["grading"],
                )

        return issues
