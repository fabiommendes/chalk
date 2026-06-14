from dataclasses import dataclass
from enum import Enum
from typing import Iterator, overload

from typing_extensions import Protocol

from ..util.parsing import Parsed
from ..util.sequence import unique
from .types import StudentId

type Disqualification = Simple | Plagiarism | Multiple

__all__ = [
    "Disqualification",
    "Plagiarism",
    "Multiple",
    "Timeout",
    "Invalid",
    "Error",
    "parse",
    "merge",
]


class DisqualificationProtocol(Protocol):
    """
    A protocol for disqualification reasons.
    """

    def message(self) -> str: ...
    def display(self) -> str: ...


def Timeout() -> Disqualification:
    """
    Indicates that a response was disqualified due to a timeout during grading.
    """
    return Simple.TIMEOUT


def Invalid() -> Disqualification:
    """
    Indicates that a response was disqualified due to invalid syntax or format.
    """
    return Simple.INVALID


def Error() -> Disqualification:
    """
    Indicates that a response was disqualified due to an internal error during grading.
    """
    return Simple.ERROR


class Simple(Enum):
    """
    An enumeration of reasons why a response might be disqualified.
    """

    TIMEOUT = "The response took too long to execute."
    INVALID = "The response contains text with an invalid syntax."
    ERROR = "Internal error during grading."

    def message(self) -> str:
        return self.value

    def display(self) -> str:
        return self.name.lower().replace("_", "-")


@dataclass(frozen=True)
class Plagiarism:
    """
    Indicates that a response was disqualified due to plagiarism from another student.
    """

    from_student: StudentId

    def message(self) -> str:
        return (
            f"The response was flagged for plagiarism from student {self.from_student}."
        )

    def display(self) -> str:
        return f"plagiarism[{self.from_student}]"


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

    def display(self) -> str:
        return "disqualified: " + ", ".join(reason.display() for reason in self.reasons)

    def iter_reasons(self) -> Iterator[Disqualification]:
        for reason in self.reasons:
            if isinstance(reason, Multiple):
                yield from reason.iter_reasons()
            else:
                yield reason


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
    if src == "timeout":
        return Parsed(src.removeprefix("timeout"), Timeout())
    if src == "invalid":
        return Parsed(src.removeprefix("invalid"), Invalid())
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

    raise ValueError(
        f"String format not supported for disqualification parsing: {src!r}"
    )


@overload
def merge(a: Disqualification, b: Disqualification) -> Disqualification: ...


@overload
def merge(
    a: Disqualification | None, b: Disqualification | None
) -> Disqualification | None: ...


def merge(
    a: Disqualification | None, b: Disqualification | None
) -> Disqualification | None:
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
