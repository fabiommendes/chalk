from typing import Any, Literal

import errorz as rz

from ..core.grader import Grader
from ..types import Answer
from .base import BaseQuestion, Issue


class FillIn(BaseQuestion[list[str]]):
    type: Literal["fill-in"] = "fill-in"  # pyright: ignore[reportIncompatibleVariableOverride]

    def get_grader(self) -> rz.Result[Grader[Any], str]:
        return rz.err("Generic questions do not support automatic grading.")

    def validate_answer(self, answer: Answer) -> rz.Result[Any, list[Issue]]:
        raise NotImplementedError
