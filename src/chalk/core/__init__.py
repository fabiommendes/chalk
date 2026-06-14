from . import disqualification
from . import question as _question
from . import submission as _submission
from .assignment import Assignment, iter_assignments
from .classroom import Classroom
from .disqualification import Disqualification
from .error import ChalkError, SystemError
from .grade import Grade
from .question import (
    AssociationQuestion,
    EssayQuestion,
    FillInQuestion,
    GenericQuestion,
    MultipleChoiceQuestion,
    MultipleSelectionQuestion,
    Question,
)
from .student import Student
from .submission import Response, Submission
from .types import Answer, AssignmentId, QuestionId, QuestionType, StudentId

__all__ = [
    "Answer",
    "Assignment",
    "AssignmentId",
    "Grade",
    "Question",
    "GenericQuestion",
    "AssociationQuestion",
    "FillInQuestion",
    "MultipleSelectionQuestion",
    "MultipleChoiceQuestion",
    "EssayQuestion",
    "QuestionId",
    "QuestionType",
    "Response",
    "Submission",
    "Student",
    "StudentId",
    "Classroom",
    "ChalkError",
    "SystemError",
    "iter_assignments",
    "disqualification",
    "Disqualification",
]


_submission.Assignment = Assignment  # type: ignore
_question.Assignment = Assignment  # type: ignore
Assignment.model_rebuild()
