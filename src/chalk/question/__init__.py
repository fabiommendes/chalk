from typing import Annotated, Any

from pydantic import Field, RootModel

from .associative import Association
from .base import Generic
from .fillin import FillIn
from .multiple_choice import MultipleChoice
from .multiple_selection import MultipleSelection
from .textual import Textual
from .util import question_id

__all__ = (
    "Question",
    "validate_question",
    "Association",
    "Generic",
    "FillIn",
    "MultipleChoice",
    "MultipleSelection",
    "Textual",
    "question_id",
)

type Question = Annotated[
    Textual | Generic | MultipleChoice | MultipleSelection | Association | FillIn,
    Field(discriminator="type"),
]


class QuestionRoot(RootModel[Question]):
    root: Question


def validate_question(data: Any) -> Question:
    """
    Convert raw data into a validated Question object.
    """
    return QuestionRoot.model_validate(data).root
