from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, NamedTuple, Protocol

import opt

from ..types import StudentId, to_decimal
from .adjustment import Adjustment
from .grade import Grade

TIMEOUT_DEFAULT = None
try:
    TIMEOUT_DEFAULT = float(os.environ.get("CHALK_AUTOGRADE_TIMEOUT", 0.0)) or None
except ValueError:
    pass
CLEAR_TEMPORARIES_DEFAULT = bool(
    os.environ.get("CHALK_AUTOGRADE_CLEAR_TEMPORARIES", "0").lower()
    in ("1", "true", "yes")
)
PREFER_LINKS_DEFAULT = bool(
    os.environ.get("CHALK_AUTOGRADE_PREFER_LINKS", "0").lower() in ("1", "true", "yes")
)


class Graded(NamedTuple):
    score: Grade | Decimal | None = None
    feedback: str | None = None
    adjustment: Adjustment | None = None

    @property
    def grade(self) -> Grade | None:
        if isinstance(self.score, Decimal):
            return Grade(self.score, adj=self.adjustment)
        elif isinstance(self.score, Grade):
            return self.score
        else:
            return None


class Grader[Answer](Protocol):
    """
    A grading function takes a student ID and an answer, and returns a
    GradingOutcome, if successful or an error message if the grading
    process fails.
    """

    def __call__(
        self, id: StudentId, answer: Answer, /, **kwargs: Any
    ) -> Graded | None: ...


@dataclass(frozen=True)
class FixedGrader(Grader[Any]):
    """
    The fixed grader always returns the same score and feedback.
    """

    score: Grade | Decimal = Decimal(0)
    feedback: str | None = None

    def __call__(self, id: StudentId, answer: Any, /, **kwargs: Any) -> Graded | None:
        return Graded(score=self.score, feedback=self.feedback)


@dataclass(frozen=True)
class Merge[T](Grader[T]):
    """
    The merge grader combines multiple graders and returns the combination of
    all grading outcomes.
    """

    graders: list[Grader[T]]
    method: Literal["sum", "max", "min", "avg"] = "sum"

    def __call__(self, id: StudentId, answer: T, /, **kwargs: Any) -> Graded | None:
        outcomes = [
            *opt.filter(grader(id, answer, **kwargs) for grader in self.graders)
        ]
        scores = [x.score for x in outcomes if x.score is not None]
        feedbacks = [x.feedback for x in outcomes if x.feedback]
        adjustments = [x.adjustment for x in outcomes if x.adjustment]

        if not scores and not feedbacks and not adjustments:
            return None

        if self.method == "sum":
            score = sum(scores, Decimal(0)) if scores else None
        elif self.method == "max":
            score = max(scores) if scores else None
        elif self.method == "min":
            score = min(scores) if scores else None
        elif self.method == "avg":
            size = len(scores)
            score = to_decimal(sum(scores) / size) if size > 0 else None
        else:
            raise ValueError(f"Invalid merge method: {self.method}")

        feedback = "\n".join(feedbacks) if feedbacks else None
        return Graded(
            score=score,
            feedback=feedback,
            adjustment=merge_adjustments(adjustments),
        )


def merge_adjustments(adjustments: list[Adjustment]) -> Adjustment | None:
    if not adjustments:
        return None
    if len(adjustments) == 1:
        return adjustments[0]

    # TODO: Implement merging multiple adjustments.
    # Adjustment must be a generic affine transform + fixed point.
    raise NotImplementedError("Merging multiple adjustments is not implemented yet")
