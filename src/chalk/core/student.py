from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from pydantic import BaseModel, Field

from ..types import StudentId

if TYPE_CHECKING:
    from .classroom import Classroom
else:
    Classroom = Any  # type: ignore


class Student(BaseModel):
    FIELDS: ClassVar[set[str]] = {"id", "name", "email", "email_alt", "github"}

    name: str
    id: StudentId
    age: int | None = None
    email: str | None = None
    email_alt: str | None = None
    github: str | None = None
    classroom: Annotated[Classroom | None, Field(repr=False, exclude=True)] = None

    def can_merge_with(self, other: Student) -> bool:
        """
        Determine if this student can be merged with another student.
        Students can be merged if they share any non-empty field value.
        """
        for key in ["id", "name", "email", "email_alt", "github"]:
            value1 = getattr(self, key)
            value2 = getattr(other, key)
            if not (value1 == value2 or value1 is None or value2 is None):
                return False
        return True

    def merge_with(self, other: Student) -> Student:
        """
        Merge this student with another student, preferring non-empty values from the new student.
        The resulting student will have the same ID as this student.
        """
        if self.id != other.id:
            raise ValueError("Cannot merge students with different IDs")

        return Student(
            id=self.id,
            name=other.name or self.name,
            email=other.email or self.email,
            email_alt=other.email_alt or self.email_alt,
            github=other.github or self.github,
        )
