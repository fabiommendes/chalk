from decimal import Decimal
from typing import Annotated, Any, Literal

#
# String Id types
#
type StudentId = Annotated[str, "A unique identifier for a student."]
type QuestionId = Annotated[str, "A unique identifier for a question."]
type AssignmentId = Annotated[str, "A unique identifier for an assignment."]

#
# Enumerations
#
QuestionType = Literal[
    "association",
    "fill-in",
    "multiple-choice",
    "multiple-selection",
    "text",
]

#
# Other basic types
#
Answer = (
    # numeric
    int
    | float
    | complex
    | Decimal
    # textual, multiple-choice
    | str
    # multiple-selection, fill-in
    | list[str]
    # association
    | dict[str, str]
)

type Numeric = int | float | Decimal


# TODO: Define a structured type for submission data.
type SubmissionData = Any


#
# Simple conversion functions
#
def to_decimal(value: Numeric | str) -> Decimal:
    """
    Convert the given numeric value to a Decimal.
    """
    if type(value) is Decimal:
        return value
    elif isinstance(value, int | float):
        return Decimal(str(value))
    return Decimal(value)
