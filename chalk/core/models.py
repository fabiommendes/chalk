from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    PlainSerializer,
    PlainValidator,
    Tag,
    model_serializer,
)

from ..data import serializers as s
from ..data import validators as v
from .adjustment import Adjustment
from .answer import AnyAnswer
from .disqualification import Disqualification
from .score import Score

log = getLogger(__name__)

if TYPE_CHECKING:
    StrictBool = bool
else:
    from pydantic import StrictBool  # type: ignore[import]

#: "A unique identifier for a student."]
StudentId = str

#: "A unique identifier for a question."]
QuestionId = str

#: "A unique identifier for a quiz."]
QuizId = str

type SerializableScore = Annotated[
    Score,
    PlainValidator(v.out_of_bounds_score),
    PlainSerializer(s.score),
]

type SerializableDisqualification = Annotated[
    Disqualification,
    PlainValidator(v.disqualification),
    PlainSerializer(s.disqualification),
]


class Classroom(BaseModel):
    """
    Serialize classroom configuration.
    """

    name: str
    teacher: str
    lang: str | None = None
    autograder: Autograder | None = None
    decimal_places: Annotated[int, Field(ge=0)] = 2

    #: Column of roster.csv with the student id. By default "school_id",
    #: or "id" in rosters without a "school_id" column.
    student_id: str | None = None


class Student(BaseModel):
    """
    Basic student model.
    """

    name: str
    email: str | None = None
    github: str | None = None
    extra: Annotated[
        dict[str, str],
        Field(default_factory=dict),
        BeforeValidator(v.clean_dict(v.any())),
    ]


class Quiz(BaseModel):
    name: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    autograder: Autograder | None = None
    questions: list[Question] | None = None
    weight: Decimal | None = None


class Response(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    answer: AnyAnswer | None = None
    start: datetime | None = None
    end: datetime | None = None

    def is_empty(self) -> bool:
        """
        True if all fields are none
        """
        return self.answer is None and self.start is None and self.end is None


class Submission(BaseModel):
    id: StudentId
    start: datetime | None = None
    end: datetime | None = None
    responses: dict[QuestionId, Response] = Field(default_factory=dict)


class ResponseGrade(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    score: SerializableScore | SerializableDisqualification
    adjustments: Annotated[
        list[Adjustment] | None,
        BeforeValidator(v.optional_list(v.serializable(Adjustment))),
        PlainSerializer(s.optional_list(s.serializable)),
    ] = None
    feedback: str | None = None


class SubmissionGrade(BaseModel):
    id: StudentId
    feedback: str | None = None
    responses: Annotated[dict[QuestionId, ResponseGrade], Field(default_factory=dict)]


# ==============================================================================
# Question Models
# ==============================================================================
type ResponseId = str
type ChoiceId = str
def _question_tag(value: Any) -> str:
    typ = value.get("type") if isinstance(value, dict) else getattr(value, "type", None)
    return "generic" if typ is None else str(typ)


type Question = Annotated[
    Annotated[Textual, Tag("text")]
    | Annotated[Repo, Tag("repo")]
    | Annotated[GenericQuestion, Tag("generic")],
    Discriminator(_question_tag),
]

#: Types of the questions defined in conf.yaml. Objective questions live in mdq
#: files under <quiz>/questions/ and carry the mdq type instead.
QuestionType = Literal[
    "text",
    "repo",
    None,  # For generic questions
]

#: Question types defined by mdq documents.
MDQ_QUESTION_TYPES = frozenset(
    {
        "multiple-choice",
        "multiple-selection",
        "true-false",
        "numeric",
        "short-answer",
        "essay",
        "fill-in",
        "ordering",
    }
)


class BaseQuestion(BaseModel):
    id: QuestionId
    name: str | None = None
    stem: str | None = None
    value: Annotated[
        Decimal | None,
        PlainSerializer(s.optional(s.decimal)),
        BeforeValidator(v.optional(v.decimal)),
    ] = None
    autograder: Autograder | None = None
    answer_suffix: str | None = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler):
        """
        Custom serialization to ensure that the `type` field is always included in the output.
        """
        data = handler(self)
        if "type" not in data:
            data = {"type": getattr(self, "type", None), **data}
        return data


class GenericQuestion(BaseQuestion):
    type: Literal[None] = None


# --- Textual/Essay questions --------------------------------------------------
class Textual(BaseQuestion):
    """
    Text-based questions.

    It can be long essays or short answers and they can display text in many
    different forms like plain text, code snippets, mathematical formulas, etc.
    """

    type: Literal["text"] = "text"
    format: Annotated[
        str | None,
        BeforeValidator(v.optional(v.text_format)),
    ] = None
    regex_validator: Annotated[
        re.Pattern[str] | None,
        BeforeValidator(v.optional(v.regex)),
        PlainSerializer(s.optional(s.regex)),
    ] = None
    regex_grader: Annotated[
        re.Pattern[str] | None,
        BeforeValidator(v.optional(v.regex)),
        PlainSerializer(s.optional(s.regex)),
    ] = None
    blank: Annotated[StrictBool, Field(default=False)]


# --- Repository based questions -----------------------------------------------
class Repo(BaseQuestion):
    type: Literal["repo"] = "repo"
    required: Annotated[
        list[str] | None,
        Field(
            description="List of required files for the repository question."
            "The question will be disclassified if some of those files are missing.",
        ),
    ] = None


# ==============================================================================
# Other configuration models
# ==============================================================================
class Autograder(BaseModel):
    answer: Annotated[
        str,
        Field(
            description=(
                "The path in the local grading repository in which the student's answer "
                "is saved to before the grading process begins."
            ),
        ),
    ] = "answer.txt"
    timeout: Annotated[
        float | None,
        Field(
            description=(
                "Default timeout (in seconds) for the autograder to run at each response. This is "
                "applicable to potentially CPU intensive grading tasks such as running test cases "
                "or executing student code."
            ),
        ),
    ] = None
    syntax: Annotated[
        bool | str | None,
        Field(
            description=(
                "If true, the autograder will automatically apply syntax validators based on the "
                "file extension of the answer or the given extension."
            ),
        ),
    ] = None
    script: Annotated[
        Path | None,
        Field(
            description=(
                "The path to a script that should be executed as part of the autograding process. "
                "The path is given relative to the question repository. Absolute paths are relative to the root of the chalk project."
            ),
        ),
    ] = None
    template: Annotated[
        Path | None,
        Field(
            description=(
                "The path to a template file that should be used to generate the autograder script. "
                "The path is given relative to the question repository. Absolute paths are relative to the root of the chalk project."
            ),
        ),
    ] = None
    command: Annotated[
        str | None,
        Field(
            description=(
                "The command to execute as part of the autograding process. This can be used "
                "as an alternative to specifying an external script."
            ),
        ),
    ] = None


#
# Necessary rebuilds
#
SubmissionGrade.model_rebuild()
ResponseGrade.model_rebuild()
