"""
Reasons a grader gives no score to an answer.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from rich.console import RenderableType
from rich.text import Text

__all__ = ["Disqualified", "Timeout", "InvalidInput", "Error", "BuildError"]


class Disqualified(Enum):
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

    def __repr__(self) -> str:
        return f"{self.name.lower().title()}()"

    def __bool__(self) -> Literal[False]:
        return False

    def __rich__(self) -> RenderableType:
        return Text(self.render(), style="red")


def Timeout() -> Disqualified:
    """
    Indicates that a response was disqualified due to a timeout during grading.
    """
    return Disqualified.TIMEOUT


def InvalidInput() -> Disqualified:
    """
    Indicates that a response was disqualified due to invalid syntax or format.
    """
    return Disqualified.INVALID_INPUT


def Error() -> Disqualified:
    """
    Indicates that a response was disqualified due to an internal error during grading.
    """
    return Disqualified.ERROR


def BuildError() -> Disqualified:
    """
    Indicates that the response does not compile, so its tests could not run.
    """
    return Disqualified.BUILD_ERROR
