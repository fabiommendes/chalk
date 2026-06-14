# TODO: Define a structured type for answers.
from __future__ import annotations

from typing import Protocol

from ..core import Answer, Disqualification, Response, StudentId


class Grader[AnswerT: Answer](Protocol):
    def qualify(
        self, response: Response, student_id: StudentId
    ) -> Disqualification | None:
        """
        Perform any necessary validation on the question before grading.

        Returns a Disqualification reason if the question is disqualified, or None otherwise.
        """
        ...

    def update_response(self, response: Response, student_id: StudentId) -> None:
        """
        Update the given response with the computed grade and feedback.

        Raises GradeError if the grade cannot be computed for the given question/answer.
        """
        ...
