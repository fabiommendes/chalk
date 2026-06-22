from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from ..types import StudentId
from .student import Student

NO_GRADE = None
SPREADSHEET_EXTENSIONS = {".csv", ".xlsx"}
STRUCTURED_DATA_EXTENSIONS = {".json", ".yaml", ".yml"}


class Classroom(BaseModel):
    name: str
    teacher: str
    lang: str | None = None
    students: dict[StudentId, Student] | None = None
    decimal_precision: Annotated[int, Field(ge=0)] = 2
