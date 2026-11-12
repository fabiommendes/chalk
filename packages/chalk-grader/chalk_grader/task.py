"""
What a grader needs to know about the question it grades.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["Task"]


# r2: adr-0002
@dataclass(frozen=True)
class Task:
    """
    The question being graded, as seen by the grader.

    The ids only label the run: they reach the script as CHALK_QUESTION and
    CHALK_QUIZ (and the deprecated CHALK_ASSIGNMENT) and are written to chalk.info.
    """

    question_id: str
    #: The quiz of the question (an exam, for codehood).
    quiz_id: str
    #: Base of the relative paths of the configuration (mounts, scoring script).
    root: Path
    #: Directory copied to the working directory before each run.
    template: Path | None = None
