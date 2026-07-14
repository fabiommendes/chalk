"""
Defines a generic "Answer" type that represent all possible answers with primitive
Python values.
"""

from decimal import Decimal
from typing import Any

from pydantic import RootModel

from ..types import JSON

FillInAnswer = list[str | None]
AssociationAnswer = dict[str, str | None]
NumericAnswer = int | float | complex | Decimal
TextualAnswer = str
MultipleChoiceAnswer = str
MultipleSelectionAnswer = list[str]
RepoAnswer = str  # Usually a path in the form responses/<student_id>/


AnyAnswer = (
    NumericAnswer
    | AssociationAnswer
    | FillInAnswer
    | TextualAnswer
    | MultipleChoiceAnswer
    | MultipleSelectionAnswer
    | RepoAnswer
)


class _AnswerModel(RootModel[AnyAnswer]):
    root: AnyAnswer


def serialize_answer(answer: AnyAnswer | None, /) -> str:
    """
    Convert the given answer to a string representation.
    """
    if answer is None:
        return ""
    if isinstance(answer, (list, set, tuple)):
        return "; ".join(map(serialize_answer, answer))
    elif isinstance(answer, dict):
        return "; ".join(f"{k}: {v}" for k, v in answer.items())
    return str(answer)


def json_serialize_answer(answer: AnyAnswer | None, /) -> JSON:
    """
    Convert the given answer to a JSON-serializable representation.
    """
    if isinstance(answer, (int, float, str, bool)) or answer is None:
        return answer
    elif isinstance(answer, Decimal):
        return float(answer)
    elif isinstance(answer, list):
        return [json_serialize_answer(a) for a in answer]
    elif isinstance(answer, dict):
        return {k: json_serialize_answer(v) for k, v in answer.items()}
    elif isinstance(answer, complex):
        return {"real": answer.real, "imag": answer.imag}
    return answer


def validate_answer(answer: Any, /) -> AnyAnswer:
    """
    Validate that the given answer is a valid answer type.
    """
    return _AnswerModel.model_validate(answer).root
