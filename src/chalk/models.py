from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel

type QuestionId = Annotated[str, "A unique identifier for a question."]
type StudentId = Annotated[str, "A unique identifier for a student."]
type AssignmentId = Annotated[str, "A unique identifier for an assignment."]
type Grade = Annotated[float, "A grade for a question or assignment."]
type Assignment = SimpleAssignment | FileAssignment

NO_GRADE = float("nan")
SPREADSHEET_EXTENSIONS = {".csv", ".xlsx"}
STRUCTURED_DATA_EXTENSIONS = {".json", ".yaml", ".yml"}


class Classroom(BaseModel):
    name: str
    teacher: str
    lang: str | None = None


class Student(BaseModel):
    name: str
    id: StudentId
    age: int | None = None
    email: str | None = None
    email_alt: str | None = None
    github: str | None = None


class Question(BaseModel):
    id: QuestionId
    type: str | None = None
    name: str | None = None
    grade: float | None = None


class BaseAssignment(BaseModel):
    id: AssignmentId
    name: str | None = None


class SimpleAssignment(BaseAssignment):
    """
    An assignment that contains the grade for each separate question.
    """

    path: Path
    start: datetime | None = None
    end: datetime | None = None
    data: dict[StudentId, SimpleAssignmentEntry]
    questions: dict[QuestionId, Question] | None = None


class SimpleAssignmentEntry(BaseAssignment):
    start: datetime | None = None
    end: datetime | None = None
    questions: dict[QuestionId, Response]


class FileAssignment(BaseAssignment):
    """
    An assignment that contains a file for each student.

    The assigment lives in a directory with the following structure:

    assignments/
        assignment_id/
            index.conf
            student1.ext
            student2.ext
            ...

    The optional index.conf file contains metadata for the assignment, and each
    student submission is stored in a file named after the student identifier
    with the appropriate extension.
    """

    files: dict[StudentId, Path]
    extensions: list[str] | None = None


class Response(BaseModel):
    answer: Any = None
    grade: Grade = NO_GRADE
    feedback: str | None = None
    start: datetime | None = None
    end: datetime | None = None


def has_grade(grade: Grade) -> bool:
    """
    Check if the grade is not NO_GRADE.
    """
    return not math.isnan(grade)
