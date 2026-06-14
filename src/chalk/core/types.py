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
# TODO: Define a structured type for answers.
type Answer = Any

# TODO: Define a structured type for submission data.
type SubmissionData = Any
