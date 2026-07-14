from __future__ import annotations

import os
from dataclasses import dataclass
from functools import reduce
from typing import Any, Callable, Iterable, Literal, NamedTuple, Protocol, TypedDict, Unpack, cast

import opt
from rich.columns import Columns
from rich.console import RenderableType
from rich.text import Text

from . import adjustment, score
from .adjustment import Adjustment
from .disqualification import Disqualification
from .models import StudentId
from .score import Score, is_score, rich_render_percent

__all__ = [
    # Basic types
    "Graded",
    "Grader",
    "GraderKwargs",
    # Constants
    "DEFAULT_TIMEOUT",
    # Grader combinators
    "FixedGrader",
    "Merged",
]

DEFAULT_TIMEOUT = 30.0
try:
    DEFAULT_TIMEOUT = float(os.environ.get("CHALK_AUTOGRADE_TIMEOUT", "30"))
except ValueError:
    pass


class Graded(NamedTuple):
    score: Score | Disqualification
    feedback: str | None = None
    adjustments: list[Adjustment] | None = None

    def adjusted_score(self) -> Score | Disqualification:
        """
        Return the score after applying all adjustments.
        """
        if not self.adjustments or isinstance(self.score, Disqualification):
            return self.score

        return cast(Score, adjustment.apply_chain(self.score, self.adjustments))

    @classmethod
    def null_score(
        cls,
        *,
        feedback: str | None = None,
        adjustments: list[Adjustment] | None = None,
    ) -> Graded:
        """
        Zero grade, with some optional feedback.
        """
        return cls(score=score.MIN_SCORE, feedback=feedback, adjustments=adjustments)

    @classmethod
    def max_score(
        cls,
        *,
        feedback: str | None = None,
        adjustments: list[Adjustment] | None = None,
    ) -> Graded:
        """
        Return a new Graded object with the score capped at max_score.
        """
        return Graded(score=score.MAX_SCORE, feedback=feedback, adjustments=adjustments)

    def __rich__(self) -> RenderableType:
        parts = []
        if isinstance(self.score, Disqualification):
            base = self.score.__rich__()
            parts.append(base)
        else:
            base = rich_render_percent(self.score)
            parts.append(base)
            if self.adjustments:
                adj_score = cast(Score, self.adjusted_score())
                parts.append(Text(" ➔ ", style="dim"))
                parts.append(rich_render_percent(adj_score))

        if self.feedback:
            parts.append(Text(f"({self.feedback})", style="dim"))

        return Columns(parts) if len(parts) > 1 else parts[0]


class GraderKwargs(TypedDict, total=False):
    debug: bool
    timeout: float
    keep_files: bool
    keep_failed: bool
    on_output_line: Callable[[str], None]


class Grader[Answer](Protocol):
    """
    A grading function takes a student ID and an answer, and returns a
    GradingOutcome, if successful or an error message if the grading
    process fails.
    """

    def __call__(
        self,
        id: StudentId,
        answer: Answer,
        /,
        **kwargs: Unpack[GraderKwargs],
    ) -> Graded | None: ...


@dataclass(frozen=True)
class FixedGrader(Grader[Any]):
    """
    The fixed grader always returns the same score and feedback.
    """

    score: Score | Disqualification = score.MIN_SCORE
    feedback: str | None = None

    def __call__(
        self,
        id: StudentId,
        answer: Any,
        /,
        **kwargs: Unpack[GraderKwargs],
    ) -> Graded | None:
        return Graded(score=self.score, feedback=self.feedback)


@dataclass(frozen=True)
class Merged[T](Grader[T]):
    """
    Combines multiple graders and returns the combination of all grading outcomes.
    """

    #: List
    graders: Iterable[Grader[T]]

    #: Aggregation method for combining scores from multiple graders.
    agg: Literal["sum", "max", "min", "avg"] = "sum"

    #: What to do if a student is disqualified by any of the graders.
    #:  - "disqualify": disqualify if any grader disqualifies them.
    #:  - "allow": if any score is available, use the score and ignore disqualifications.
    #:  - "skip": skip all disqualifications. Yield a null score if all graders disqualify the student.
    disqualification: Literal["disqualify", "allow, skip"] = "disqualify"

    def __post_init__(self) -> None:
        if not self.graders:
            raise ValueError("Merge grader must have at least one grader.")
        self.__setattr__("graders", tuple(self.graders))

    def __call__(
        self,
        id: StudentId,
        answer: T,
        /,
        **kwargs: Unpack[GraderKwargs],
    ) -> Graded | None:
        outcomes = [*opt.filter(grader(id, answer, **kwargs) for grader in self.graders)]
        scores = [cast(Score, x.adjusted_score()) for x in outcomes if is_score(x.score)]
        disqualifications = [(i, x.score) for i, x in enumerate(outcomes) if not is_score(x.score)]

        if disqualifications:
            method = self.disqualification
            if method == "disqualify" or method == "allow" and not scores:
                return outcomes[disqualifications[0][0]]
            elif method == "skip" and not scores:
                return Graded(score=score.MIN_SCORE, feedback="No valid scores available.")

        disqualified_locs = {i for i, x in enumerate(outcomes) if not is_score(x.score)}
        size = len(scores)
        if size == 1:
            for outcome in outcomes:
                if is_score(outcome.score):
                    return outcome

        if self.agg == "sum":
            agg = reduce(score.add, scores, score.MIN_SCORE)
        elif self.agg == "max":
            agg = max(scores)
        elif self.agg == "min":
            agg = min(scores)
        elif self.agg == "avg":
            agg = score.div(reduce(score.add, scores, score.MIN_SCORE), size)
        else:
            raise ValueError(f"Invalid merge method: {self.agg}")

        feedbacks = [
            x.feedback for i, x in enumerate(outcomes) if i not in disqualified_locs and x.feedback
        ]
        feedback = "\n".join(feedbacks) if feedbacks else None
        return Graded(
            score=agg,
            feedback=feedback,
        )
