from .. import question
from ..question import Question
from . import disqualification, models
from .answer import AnyAnswer, validate_answer
from .classroom import Classroom
from .disqualification import Disqualification
from .error import ChalkError, ChalkErrorEnum
from .models import QuestionId, QuestionType, QuizId, StudentId
from .quiz import Quiz
from .student import Student

INVALID_ASSIGNMENT_NAMES = {
    "chalk",
    "roster",
    "data",
    "conf",
    "reports",
    "scripts",
}

__all__ = [
    "AnyAnswer",
    "ChalkError",
    "ChalkErrorEnum",
    "Classroom",
    "disqualification",
    "Disqualification",
    "models",
    "question",
    "Question",
    "QuestionId",
    "QuestionType",
    "Quiz",
    "QuizId",
    "Student",
    "StudentId",
    "validate_answer",
    "validate_quiz_id",
    # "Response",
    # "Submission",
]


def validate_question_id(src: str) -> QuestionId:
    """
    Return a valid QuestionId from string or raise ValueError.
    """
    return _validate_entity_id(src, "question")


def validate_quiz_id(src: str) -> QuizId:
    """
    Return a valid QuizId from string or raise ValueError.
    """
    return _validate_entity_id(src, "quiz")


def _validate_entity_id(src: str, /, entity: str) -> str:
    if src in INVALID_ASSIGNMENT_NAMES:
        raise ValueError(f"Invalid {entity} name: {src!r}")
    if src.startswith("_"):
        raise ValueError(f"{entity.title()} names cannot start with '_'")
    if src.startswith("."):
        raise ValueError(f"{entity.title()} names cannot start with '.'")
    return src
