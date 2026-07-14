from typing import cast

from ..core import models
from ..core.answer import AnyAnswer, FillInAnswer
from .base import BaseQuestion, type_error


class FillIn(BaseQuestion[models.FillIn, FillInAnswer]):
    def validate_answer(self, answer: AnyAnswer) -> FillInAnswer:
        if not isinstance(answer, list):
            raise type_error("Answer must be a list of strings.")

        for i, a in enumerate(answer):
            if not isinstance(a, str):
                msg = f"Answer at index {i} is {type(a).__name__}, expected str or empty."
                raise type_error(msg)

        return cast(FillInAnswer, answer)
