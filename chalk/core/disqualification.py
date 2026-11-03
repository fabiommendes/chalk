from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, TypeIs, overload

from rich.console import RenderableType
from rich.text import Text

from ..util.parsing import Parsed
from ..util.sequence import unique

if TYPE_CHECKING:
    from .models import StudentId

__all__ = [
    "Disqualification",
    "Plagiarism",
    "Multiple",
    "Timeout",
    "InvalidInput",
    "Error",
    "BuildError",
    "parse",
    "merge",
]


def Timeout() -> Disqualification:
    """
    Indicates that a response was disqualified due to a timeout during grading.
    """
    return Simple.TIMEOUT


def InvalidInput() -> Disqualification:
    """
    Indicates that a response was disqualified due to invalid syntax or format.
    """
    return Simple.INVALID_INPUT


def Error() -> Disqualification:
    """
    Indicates that a response was disqualified due to an internal error during grading.
    """
    return Simple.ERROR


def BuildError() -> Disqualification:
    """
    Indicates that the response does not compile, so its tests could not run.
    """
    return Simple.BUILD_ERROR


class Simple(Enum):
    """
    An enumeration of reasons why a response might be disqualified.
    """

    TIMEOUT = "The response took too long to execute."
    INVALID_INPUT = "The response contains text with an invalid syntax."
    ERROR = "Internal error during grading."
    BUILD_ERROR = "The response does not compile."

    def message(self) -> str:
        return self.value

    def render(self) -> str:
        return self.name.lower().replace("_", "-")

    def __str__(self) -> str:
        return self.render()

    def __lt__(self, other: Disqualification) -> Disqualification:
        if not isinstance(other, Disqualification):
            return NotImplemented
        return merge(self, other)

    def __repr__(self) -> str:
        return f"{self.name.lower().title()}()"

    def __bool__(self) -> Literal[False]:
        return False

    def __rich__(self) -> RenderableType:
        return Text(self.render(), style="red")


@dataclass(frozen=True)
class Plagiarism:
    """
    Indicates that a response was disqualified due to plagiarism from another student.
    """

    from_student: StudentId

    def message(self) -> str:
        return f"The response was flagged for plagiarism from student {self.from_student}."

    def render(self) -> str:
        return f"plagiarism[{self.from_student}]"

    def __lt__(self, other: Disqualification) -> Disqualification:
        if not isinstance(other, Disqualification):
            return NotImplemented
        return merge(self, other)

    def __str__(self) -> str:
        return self.render()

    def __bool__(self) -> Literal[False]:
        return False

    def __rich__(self) -> RenderableType:
        return Text(self.render(), style="red")


@dataclass(frozen=True)
class Multiple:
    """
    Aggregates multiple disqualification reasons into a single reason.
    """

    reasons: tuple[Disqualification, ...]

    def __post_init__(self) -> None:
        raise RuntimeError(
            "Cannot create a Multiple disqualification directly. Use the merge function instead."
        )

    def message(self) -> str:
        return "The response was disqualified for the following reasons:\n" + "\n".join(
            f"- {reason.message()}" for reason in self.reasons
        )

    def render(self) -> str:
        return "disqualified: " + ", ".join(reason.render() for reason in self.reasons)

    def iter_reasons(self) -> Iterator[Disqualification]:
        for reason in self.reasons:
            if isinstance(reason, Multiple):
                yield from reason.iter_reasons()
            else:
                yield reason

    def __lt__(self, other: Disqualification) -> Disqualification:
        if not isinstance(other, Disqualification):
            return NotImplemented
        return merge(self, other)

    def __repr__(self) -> str:
        return " | ".join(repr(reason) for reason in self.reasons)

    def __str__(self) -> str:
        return self.render()

    def __bool__(self) -> Literal[False]:
        return False

    def __rich__(self) -> RenderableType:
        return Text(self.render(), style="red")


def parse(src: str) -> Disqualification:
    """
    Parse a disqualification from a string representation.
    """
    [rest, dis] = read(src)
    if rest:
        msg = f"Unexpected trailing characters after disqualification: {rest!r}"
        raise ValueError(msg)
    return dis


def read(src: str) -> Parsed[Disqualification]:
    """
    Parse a disqualification from the start of the string.

    Raise ValueError for invalid strings.
    """
    if src.startswith("timeout"):
        return Parsed(src.removeprefix("timeout"), Timeout())

    for prefix in ("invalid-input", "invalid input"):
        if src.startswith(prefix):
            return Parsed(src.removeprefix(prefix), InvalidInput())

    if src.startswith("build-error"):
        return Parsed(src.removeprefix("build-error"), BuildError())

    if src.startswith("error"):
        return Parsed(src.removeprefix("error"), Error())

    if src.startswith("plagiarism[") and "]" in src:
        from_student, sep, rest = src.removeprefix("plagiarism[").partition("]")
        if sep:
            return Parsed(rest, Plagiarism(from_student))

    if src.startswith("disqualified: "):
        reasons: list[Disqualification] = []
        rest = src.removeprefix("disqualified: ")
        while True:
            try:
                [rest, reason] = read(rest)
                reasons.append(reason)
            except ValueError:
                break

            # Continue reading if find a
            if rest.startswith(", "):
                rest = rest.removeprefix(", ")
                continue

            # Now we have read every reason, return
            result: Disqualification = _multiple(reasons)  # type: ignore
            return Parsed(rest, result)

    raise ValueError(f"String format not supported for disqualification parsing: {src!r}")


#
# The disqualification type
#
# We define here because we need it during runtime.
Disqualification = Simple | Plagiarism | Multiple


def is_disqualification(obj: Any, /) -> TypeIs[Disqualification]:
    """
    True if argument is a disqualification.
    """
    return isinstance(obj, (Simple, Plagiarism, Multiple))


@overload
def merge(a: Disqualification, b: Disqualification) -> Disqualification: ...


@overload
def merge(a: Disqualification | None, b: Disqualification | None) -> Disqualification | None: ...


def merge(a: Disqualification | None, b: Disqualification | None) -> Disqualification | None:
    """
    Merge two disqualifications into a single disqualification.
    """
    if a is None:
        return b
    if b is None:
        return a

    reasons = unique(_reasons(a) + _reasons(b))
    return _multiple(reasons)


def _reasons(disqualification: Disqualification) -> list[Disqualification]:
    if isinstance(disqualification, Multiple):
        return list(disqualification.iter_reasons())
    else:
        return [disqualification]


def _multiple(reasons: list[Disqualification]) -> Disqualification | None:
    if len(reasons) == 1:
        return reasons[0]
    elif len(reasons) == 0:
        return None

    new = object.__new__(Multiple)
    object.__setattr__(new, "reasons", tuple(reasons))
    return new
