from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from logging import getLogger
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

from chalk_grader.models import (  # noqa: F401
    Autograder,
    Limits,
    PrepareStep,
    Profile,
    ProfileStep,
    Service,
    Stage,
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
    #: Autograder profiles of the [profiles] tables, before validation:
    #: `extends` is resolved by chalk_grader.profile_grader.
    profiles: dict[str, dict[str, Any]] = {}

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
    notes: Annotated[
        str | None,
        Field(description="Notes for the teacher, such as signs of tampering. Not for students."),
    ] = None


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
    #: Path to an mdq file outside <quiz>/questions/, relative to the quiz
    #: directory (e.g. ../questions/recursion/01.md in a codehood course).
    source: str | None = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler):
        """
        Custom serialization to ensure that the `type` field is always included in the output.
        """
        data = handler(self)
        if "type" not in data and getattr(self, "type", None) is not None:
            data = {"type": self.type, **data}
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
#
# Necessary rebuilds
#
SubmissionGrade.model_rebuild()
ResponseGrade.model_rebuild()
