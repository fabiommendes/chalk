import operator
from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Literal, Mapping

import errorz as rz
import opt
from rich.console import RenderableType

from ..core import disqualification as dis
from ..core import models
from ..core.answer import AnyAnswer, MultipleChoiceAnswer
from ..core.grader import Graded
from ..core.models import (
    Choice,
    ChoiceId,
    Response,
    StudentId,
)
from .base import (
    Issue,
    empty_result,
    fail,
    validate_type,
)
from .choices import (
    ChoiceQuestionBase,
    display_choices,
)
from .renderable import RenderableField
from .util import merge_errors


class MultipleChoice(ChoiceQuestionBase[models.MultipleChoice, MultipleChoiceAnswer]):
    """
    A question in which students mark a single answer from a list of options.

    The answer is the id of the selected choice. The grade is determined by the
    grade associated with the selected choice.
    """

    @property
    def penalty(self) -> Literal["fair", "negative", "half", "third"] | Decimal | None:
        return self._conf.penalty

    def validate_answer(self, answer: AnyAnswer | str) -> MultipleChoiceAnswer:
        value = validate_type(answer, str)
        if not value:
            raise empty_result()

        if value not in self._choices:
            raise fail(
                "invalid-choice",
                f"Selected choice does not exist: {value!r}.",
                scopes=["response"],
            )
        return value

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

    def _render_base_fields(self, plain: bool = False) -> Iterable[tuple[str, RenderableField]]:
        yield from super()._render_base_fields(plain)
        yield "penalty", str(self.penalty)

    def _render_base_sections(self, plain: bool = False) -> Iterable[RenderableType]:
        yield from super()._render_base_sections(plain)
        yield from display_choices(self._choices.values(), plain=plain)

    #
    # Grading methods
    #
    def grade_answer(self, id: MultipleChoiceAnswer) -> Graded | None:
        """
        Grade the given answer and return the grade as a decimal between 0 and 1.

        This is a helper method that can be used by graders for this question type.
        """
        choice = self.get_choice(id)

        # Disqualify missing choices
        if choice is None:
            return Graded(dis.InvalidInput())
        return Graded(choice.value)

    #
    # Utility methods
    #
    def _get_grading_issues(self) -> Iterable[Issue]:
        # Must have at least one choice with the maximum grade.
        grades = [choice.value for choice in self._choices.values() if choice.value is not None]
        if max(grades, default=0) < 1:
            yield Issue.error(
                "no-correct-choice",
                "Multiple choice question has no correct choice.",
                scopes=["grading"],
            )

    def _infer_choices_from_responses(
        self, responses: Mapping[StudentId, models.Response]
    ) -> tuple[dict[ChoiceId, Choice], list[Issue]]:
        """
        Infer the choices for this question from the given responses.

        This is used to provide feedback to instructors when they create or edit questions without explicitly providing choices, but there are already responses with answers that can be used to infer the choices.
        """
        choice_grades: dict[ChoiceId, set[Decimal | None]] = defaultdict(set)
        for response in responses.values():
            answer = response.answer
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
                        grade /= self.value
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
        self, responses: Mapping[StudentId, models.Response]
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
