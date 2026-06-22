from .. import question
from .. import question as _question
from ..question import Question
from ..types import Answer, AssignmentId, QuestionId, QuestionType, StudentId
from . import disqualification
from . import submission as _submission
from .assignment import Assignment, iter_assignments
from .classroom import Classroom
from .disqualification import Disqualification
from .error import ChalkError, SystemError
from .grade import Grade
from .student import Student
from .submission import Response, Submission

INVALID_ASSIGNMENT_NAMES = {
    "chalk",
    "roster",
    "data",
    "conf",
    "reports",
    "scripts",
}

__all__ = [
    "Answer",
    "Assignment",
    "AssignmentId",
    "Grade",
    "question",
    "Question",
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
    "validate_assignment_id",
]


_submission.Assignment = Assignment  # type: ignore
_question.Assignment = Assignment  # type: ignore
Assignment.model_rebuild()


def validate_question_id(src: str) -> QuestionId:
    """
    Return a valid QuestionId from string or raise ValueError.
    """
    return _validate_entity_id(src, "question")


def validate_assignment_id(src: str) -> AssignmentId:
    """
    Return a valid AssignmentId from string or raise ValueError.
    """
    return _validate_entity_id(src, "assignment")


def _validate_entity_id(src: str, /, entity: str) -> str:
    if src in INVALID_ASSIGNMENT_NAMES:
        raise ValueError(f"Invalid {entity} name: {src!r}")
    if src.startswith("_"):
        raise ValueError(f"{entity.title()} names cannot start with '_'")
    if src.startswith("."):
        raise ValueError(f"{entity.title()} names cannot start with '.'")
    return src
