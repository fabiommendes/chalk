from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from weakref import proxy, ref

import opt

from ..util import clean_data
from . import models
from .models import StudentId

if TYPE_CHECKING:
    from .classroom import Classroom


@dataclass(init=False)
class Student:
    """
    A class representing a student with their configuration and information.
    """

    id: StudentId
    name: str
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def classroom(self) -> Classroom:
        if (cls := self._classroom()) is not None:
            return cls
        raise RuntimeError("Classroom reference is no longer valid.")

    def __and__(self, value: Any) -> Student | None:
        if isinstance(value, Student):
            return self.merge_with(value)
        elif value is None:
            return self.copy()
        return NotImplemented

    def __rand__(self, value: Any) -> Student | None:
        if value is None:
            return self.copy()
        return NotImplemented

    def __init__(self, id: StudentId, name: str, classroom: Classroom, **extra: str | None):
        self.id = id
        self.name = name
        self._classroom = ref(classroom)
        self.extra = clean_data(extra)

    #
    # Common generic attributes for students
    #
    @property
    def email(self) -> str | None:
        return self.extra.get("email")

    @email.setter
    def email(self, value: str | None) -> None:
        if value is None:
            self.extra.pop("email", None)
        else:
            self.extra["email"] = value

    @property
    def github(self) -> str | None:
        return self.extra.get("github")

    @github.setter
    def github(self, value: str | None) -> None:
        if value is None:
            self.extra.pop("github", None)
        else:
            self.extra["github"] = value

    @property
    def status(self) -> str:
        """
        Enrollment status: "active" (the default) or "dropped".
        """
        return self.extra.get("status") or "active"

    @property
    def active(self) -> bool:
        return self.status != "dropped"

    @classmethod
    def from_model(cls, id: StudentId, model: models.Student, /, classroom: Classroom) -> Student:
        """
        Create a Student instance from a Student model and a Classroom.
        """
        return cls(
            id=id,
            name=model.name,
            classroom=proxy(classroom),
            **clean_data({"email": model.email, "github": model.github}),
        )

    @classmethod
    def from_json(cls, data: dict[str, Any], classroom: Classroom) -> Student:
        """
        Create a Student instance from a JSON-like dictionary and a Classroom.
        """
        data = clean_data(data)
        try:
            id = data.pop("id")
            name = data.pop("name", id)
        except KeyError as e:
            raise ValueError(f"Missing required field: {e.args[0]}") from e

        return cls(id=id, name=name, classroom=proxy(classroom), **data)

    def __repr__(self) -> str:
        return f"Student({self.id!r}, name={self.name!r})"

    def can_merge_with(self, other: Student) -> bool:
        """
        Determine if this student can be merged with another student.
        Students can be merged if they share any non-empty field value.
        """
        if self.classroom != other.classroom or self.id != other.id:
            return False

        # We merge different names if none of them is empty or equal to
        # the id.
        names = {self.name, other.name} - {"", self.id}
        if len(names) > 1:
            return False

        return {**self.extra, **other.extra} == {**other.extra, **self.extra}

    def merge_with(self, other: Student) -> Student | None:
        """
        Merge this student with another student, preferring non-empty values from the new student.
        The resulting student will have the same ID as this student.
        """
        if not self.can_merge_with(other):
            return None

        # We pick the most informative name. Ids are equal if they can be
        # merged
        names = {self.name, other.name} - {"", self.id}
        name = names.pop() if names else self.name

        return Student(
            id=self.id,
            name=name,
            classroom=self.classroom,
            **self.extra,
            **other.extra,
        )

    def copy(self, *, classroom: Classroom | None = None, **kwargs) -> Student:
        """
        Create a copy of this student.
        """
        return Student(
            id=self.id,
            name=self.name,
            classroom=opt.map(proxy, classroom) or self.classroom,
            **self.extra,
        )
