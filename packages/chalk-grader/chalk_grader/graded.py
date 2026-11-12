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

__all__ = ["DEFAULT_TIMEOUT", "Graded"]

DEFAULT_TIMEOUT = 30.0
try:
    DEFAULT_TIMEOUT = float(os.environ.get("CHALK_AUTOGRADE_TIMEOUT", "30"))
except ValueError:
    pass


class Graded(NamedTuple):
    #: A score or a disqualification (chalk_grader.disqualification, or a
    #: richer type of the caller with the same interface).
    score: Score | Any
    feedback: str | None = None
    #: Notes for the teacher, such as signs of tampering. Never shown to
    #: the student.
    notes: str | None = None

    def __rich__(self) -> RenderableType:
        parts: list[RenderableType] = []
        if is_score(self.score):
            parts.append(rich_render_percent(self.score))
        else:
            parts.append(self.score.__rich__())
        if self.feedback:
            parts.append(Text(f"({self.feedback})", style="dim"))
        return Columns(parts) if len(parts) > 1 else parts[0]
