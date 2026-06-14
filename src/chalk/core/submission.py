from __future__ import annotations

from datetime import datetime
from operator import methodcaller
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer

from ..data import serializers as s
from ..data import validators as v
from .grade import Grade, validate_grade
from .types import Answer, QuestionId, SubmissionData

if TYPE_CHECKING:
    from .assignment import Assignment

__all__ = [
    "Submission",
    "Response",
]


class Submission(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    data: SubmissionData | None = None
    responses: dict[QuestionId, Response]

    # Parent reference
    _assignment: Annotated[
        Assignment | None,
        Field(repr=False, exclude=True),
    ] = None


class Response(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    answer: Answer | None = None
    feedback: str | None = None
    grade: Annotated[
        Grade | None,
        BeforeValidator(v.optional(validate_grade)),
        PlainSerializer(s.optional(methodcaller("to_json"))),
    ] = None
    start: datetime | None = None
    end: datetime | None = None
    base_path: Path | None = None

    # Parent references
    _submission: Annotated[
        Submission | None,
        Field(repr=False, exclude=True),
    ] = None
