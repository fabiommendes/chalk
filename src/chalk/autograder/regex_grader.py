from dataclasses import dataclass
from decimal import Decimal
from re import Pattern
from typing import Any, Literal

from ..core import StudentId
from ..core.grader import Graded, Grader


@dataclass(frozen=True)
class RegexGrader(Grader[str]):
    """
    Grades based on a regular expression.

    The answer is considered correct if it matches the regex.
    """

    pattern: Pattern[str]
    grade: Decimal = Decimal(1)
    match: Literal["full", "search", "start"] = "full"

    def __call__(self, id: StudentId, answer: str, /, **kwargs: Any) -> Graded | None:
        if self.match == "full" and self.pattern.fullmatch(answer):
            return Graded(self.grade)
        elif self.match == "search" and self.pattern.search(answer):
            return Graded(self.grade)
        elif self.match == "start" and self.pattern.match(answer):
            return Graded(self.grade)
        else:
            return Graded(score=Decimal(0))
