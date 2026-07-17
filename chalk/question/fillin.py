from ..core import models
from ..core.answer import AnyAnswer, FillInAnswer
from .base import BaseQuestion, type_error


class FillIn(BaseQuestion[models.FillIn, FillInAnswer]):
    def validate_answer(self, answer: AnyAnswer) -> FillInAnswer:
        if not isinstance(answer, (list, tuple)):
            raise type_error("Answer must be a list of strings.")

        ans = tuple(answer)
        for i, a in enumerate(ans):
            if a is not None and not isinstance(a, str):
                msg = f"Answer at index {i} is {type(a).__name__}, expected str or empty."
                raise type_error(msg)

        return ans
