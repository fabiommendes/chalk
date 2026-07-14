from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from functools import partial
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Callable, Literal, NotRequired, TypedDict

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    RootModel,
    ValidatorFunctionWrapHandler,
    WrapValidator,
    model_serializer,
    model_validator,
)

from ..data import serializers as s
from ..data import validators as v
from ..util import clean_data
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
    responses: Annotated[dict[QuestionId, Response], Field(default_factory=dict)]


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
type Question = Annotated[
    Association | MultipleChoice | MultipleSelection | Textual | FillIn | GenericQuestion | Repo,
    Field(discriminator="type"),
]

QuestionType = Literal[
    "association",
    "fill-in",
    "multiple-choice",
    "multiple-selection",
    "text",
    "repo",
    None,  # For generic questions
]


class BaseQuestion(BaseModel):
    id: QuestionId
    name: str | None = None
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


# --- Multiple Choice/Multiple selection ---------------------------------------
type MultipleChoicePenalty = Literal["fair", "negative"] | Decimal


def validate_choices(
    choices: Any,
    handler: ValidatorFunctionWrapHandler,
    choice: Literal["choice", "association"] = "choice",
) -> list[Choice] | None:
    try:
        return handler(choices)
    except ValueError as e:
        error = e

    cls = Choice if choice == "choice" else AssociationChoice

    try:
        return match_root(
            choices, {
                _ListOfStrings:     lambda lst: [cls(id=id) for id in lst],
                _DictOfOptStrings:  lambda d: [cls(id=id, text=text) for id, text in d.items()],
                _DictOfOptDecimals: lambda d: [cls(id=id, value=value or Decimal(0)) for id, value in d.items()],
            },
        )  # fmt: skip
    except ValueError:
        raise error


class ChoiceAnswerDict(TypedDict):
    id: ChoiceId
    text: NotRequired[str]


class Choice(BaseModel):
    id: ChoiceId
    text: str | None = None
    value: Annotated[
        Decimal,
        PlainSerializer(s.optional(s.decimal)),
        BeforeValidator(v.optional(v.decimal)),
    ] = Decimal(0)

    @property
    def title(self) -> str:
        return self.text or self.id


class MultipleChoice(BaseQuestion):
    """
    A question in which students mark a single answer from a list of options.

    The answer is the id of the selected choice. The grade is determined by the
    grade associated with the selected choice.
    """

    type: Literal["multiple-choice"] = "multiple-choice"
    penalty: MultipleChoicePenalty | None = None
    choices: Annotated[
        list[Choice] | None,
        WrapValidator(validate_choices),
        AfterValidator(v.unique_by(lambda x: x.id, type=Choice, nullable=True)),
    ] = None


class MultipleSelection(BaseQuestion):
    """
    A question in which students mark multiple answers from a list of options.

    The answer is a list of ids of the selected choices. The grade is determined
    by the grades associated with the selected choices using the sum, mean, product,
    or min aggregation method.
    """

    type: Literal["multiple-selection"] = "multiple-selection"
    grading_method: Literal["sum", "all-or-nothing", "min", "mean"] = "sum"
    choices: Annotated[
        list[Choice] | None,
        WrapValidator(validate_choices),
        AfterValidator(v.unique_by(lambda x: x.id, type=Choice, nullable=True)),
    ] = None


# --- Association Question -----------------------------------------------------
type AssociationAnswerKey = dict[ChoiceId, ResponseId | None]
type AssociationGradingMethod = Literal["sum", "all-or-nothing"]


def validate_responses(
    value: Any, handler: ValidatorFunctionWrapHandler
) -> list[AssociationResponse] | None:
    try:
        return handler(value)
    except ValueError as e:
        error = e

    try:
        return match_root(
            value, {
                _ListOfStrings:     lambda lst: [AssociationResponse(id=id) for id in lst],
                _DictOfOptStrings:  lambda d: [AssociationResponse(id=id, text=text) for id, text in d.items()],
            },
        )  # fmt: skip
    except ValueError:
        raise error


class AssociationChoice(Choice):
    response: ResponseId | None = None


class AssociationResponse(BaseModel):
    id: ResponseId
    text: str | None = None

    @property
    def title(self) -> str:
        return self.text or self.id


class Association(BaseQuestion):
    type: Literal["association"] = "association"
    grading_method: AssociationGradingMethod = "sum"
    unique: Annotated[
        StrictBool | None,
        Field(description="Whether each response can be selected only once."),
    ] = None
    choices: Annotated[
        list[AssociationChoice] | None,
        WrapValidator(partial(validate_choices, choice="association")),
        AfterValidator(v.unique_by(v.id, nullable=True, type=AssociationChoice)),
    ] = None
    responses: Annotated[
        list[AssociationResponse] | None,
        WrapValidator(validate_responses),
        AfterValidator(v.unique_by(v.id, nullable=True, type=AssociationResponse)),
    ] = None
    answer_key: Annotated[
        AssociationAnswerKey | None,
        Field(
            description=(
                "The correct answer key for the question. Can be given instead "
                "of the `response` field in each choice."
            ),
        ),
    ] = None

    @model_validator(mode="after")
    def validate_answer_key(self) -> Association:
        """
        Normalize the answer key field and save all associations in the choices'
        response fields.
        """
        if self.answer_key is None:
            return self

        # Validate ids in answer_key
        responses = {response.id: response for response in self.responses or ()}
        choices = {choice.id: choice for choice in self.choices or ()}

        for choice_id, response_id in self.answer_key.items():
            if response_id not in responses:
                raise ValueError("Invalid answer key: response ID {response_id!r} not found.")
            if choice_id not in choices:
                raise ValueError("Invalid answer key: choice ID {choice_id!r} not found.")

        # They should also be consistent with the choices' response fields if they are set
        partial_key = clean_data({choice.id: choice.response for choice in self.choices or ()})

        for choice_id, response_id in self.answer_key.items():
            if choice_id not in partial_key:
                choices[choice_id].response = response_id
            elif choice_id in partial_key and partial_key[choice_id] != response_id:
                raise ValueError(
                    f"Answer key for choice {choice_id!r} conflicts with choice response: "
                    f"{response_id!r} != {partial_key[choice_id]!r}"
                )

        self.answer_key = None
        return self


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
    plagiarism: Annotated[
        Plagiarism | None,
        Field(
            exclude=True,
            description=(
                "The plagiarism detection configuration for this question. "
                "This is used to access the question's reference and "
                "placeholder values."
            ),
        ),
    ] = None


# --- Fill-in-the-blank questions ----------------------------------------------
class FillIn(BaseQuestion):
    type: Literal["fill-in"] = "fill-in"


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
    plagiarism: Annotated[
        Plagiarism | None,
        Field(
            exclude=True,
            description=(
                "The plagiarism detection configuration for this question. "
                "This is used to access the question's reference and "
                "placeholder values."
            ),
        ),
    ] = None


# ==============================================================================
# Other configuration models
# ==============================================================================
class Plagiarism(BaseModel):
    """
    Plagiarism configuration model
    """

    databases: Annotated[
        dict[str, PlagiarismFileSystemDb | PlagiarismChalkDb],
        Field(
            description=("A list of historical databases to use for plagiarism detection."),
            default_factory=dict,
        ),
    ]
    variance: Annotated[
        Literal["low", "medium", "high"] | None,
        Field(
            description=(
                "Calibrates the plagiarism detection using the information if students' answers "
                "are suposed to be similar to each other or not."
            ),
        ),
    ] = None
    min_grade: Annotated[
        float | None,
        Field(
            description=(
                "Minimum grade assigned to submission to consider it for plagiarism detection."
            ),
        ),
    ] = 0.0


class PlagiarismFileSystemDb(BaseModel):
    """
    A database of submissions stored in the filesystem.
    """

    path: Path
    suffix: str | None
    include: str | None
    exclude: str | None


class PlagiarismChalkDb(BaseModel):
    """
    A database of submissions stored in another Chalk classroom.
    """

    path: Path
    quiz: str
    question: str
    min_grade: float | None = None


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


#
# Utility models and functions
#
class _ListOfStrings(RootModel):
    root: list[str]


class _DictOfOptStrings(RootModel):
    root: dict[str, str | None]


class _DictOfOptDecimals(RootModel):
    root: dict[str, Decimal | None]


def match_root(obj: Any, validators: dict[type[RootModel], Callable[[Any], Any]], /) -> Any:
    """
    Match a root model based on the given validators.

    This is used to match a root model based on the type of the root field.
    """
    for model, validator in validators.items():
        try:
            result = model.model_validate(obj).root
        except ValueError:
            continue
        else:
            return validator(result)
    raise ValueError("No matching root model found.")
