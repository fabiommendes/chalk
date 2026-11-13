"""
The result of grading one answer.
"""

from __future__ import annotations

import os
from typing import Any, NamedTuple

from rich.columns import Columns
from rich.console import RenderableType
from rich.text import Text

from .score import Score, is_score, rich_render_percent

__all__ = ["DEFAULT_TIMEOUT", "CaseResult", "Graded"]

DEFAULT_TIMEOUT = 30.0
try:
    DEFAULT_TIMEOUT = float(os.environ.get("CHALK_AUTOGRADE_TIMEOUT", "30"))
except ValueError:
    pass


class CaseResult(NamedTuple):
    """
    The outcome of one expected test of a run.
    """

    #: (classname, name) of the test in the JUnit report, or the case id of a
    #: stdio report.
    key: tuple[str, str]
    #: The name shown in the feedback.
    name: str
    passed: bool
    #: Why the test failed: its message, or "(not run)".
    message: str | None = None


class Graded(NamedTuple):
    #: A score or a disqualification (chalk_grader.disqualification, or a
    #: richer type of the caller with the same interface).
    score: Score | Any
    feedback: str | None = None
    #: Notes for the teacher, such as signs of tampering. Never shown to
    #: the student.
    notes: str | None = None
    #: One entry per expected test, in the order of the reference run, when
    #: the result came from a test report. None otherwise (a script, a build
    #: error, a timeout).
    cases: tuple[CaseResult, ...] | None = None

    def __rich__(self) -> RenderableType:
        parts: list[RenderableType] = []
        if is_score(self.score):
            parts.append(rich_render_percent(self.score))
        else:
            parts.append(self.score.__rich__())
        if self.feedback:
            parts.append(Text(f"({self.feedback})", style="dim"))
        return Columns(parts) if len(parts) > 1 else parts[0]
