"""
Defines a generic "Answer" type that represent all possible answers with primitive
Python values.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from frozendict import frozendict

from chalk.data import yaml

from ..data.validators import typecheck
from ..types import JSON

if TYPE_CHECKING:
    pass

MappingAnswer = frozendict[str, Any]
ListAnswer = tuple[Any, ...]
NumericAnswer = int | float | Decimal
TextualAnswer = str
MultipleChoiceAnswer = str
RepoAnswer = str  # Usually a path in the form responses/<student_id>/


AnyAnswer = (
    NumericAnswer
    | MappingAnswer
    | ListAnswer
    | TextualAnswer
    | MultipleChoiceAnswer
    | RepoAnswer
)


def serialize_any_answer(answer: AnyAnswer | None, /) -> str:
    """
    Convert the given answer to a string representation.
    """
    if answer is None:
        return ""
    if isinstance(answer, (list, set, tuple)):
        return yaml.dumps(list(answer))
    elif isinstance(answer, (dict, frozendict)):
        return yaml.dumps(answer)
    return str(answer)


def json_serialize_any_answer(answer: AnyAnswer | None, /) -> JSON:
    """
    Convert the given answer to a JSON-serializable representation.
    """
    if isinstance(answer, (int, float, str, bool)) or answer is None:
        return answer
    elif isinstance(answer, Decimal):
        return float(answer)
    elif isinstance(answer, (list, tuple)):
        return [json_serialize_any_answer(a) for a in answer]
    elif isinstance(answer, (dict, frozendict)):
        return {k: json_serialize_any_answer(v) for k, v in answer.items()}
    elif isinstance(answer, complex):
        return {"real": answer.real, "imag": answer.imag}
    return answer


def validate_any_answer(answer: Any, /) -> AnyAnswer:
    """
    Validate that the given answer is a valid answer type.
    """
    if isinstance(answer, (int, float, Decimal, str)):
        return answer
    elif isinstance(answer, Mapping):
        return frozendict({_is_str(k): v for k, v in answer.items()})

    try:
        return tuple(a if a is None else _is_str(a) for a in answer)
    except TypeError:
        raise ValueError(f"Invalid answer type: {type(answer)}")


_is_str = typecheck(str)


def parse_any_answer(
    answer: str, /, mode: str | None = None, error: Literal["raise", "ignore"] = "raise"
) -> AnyAnswer:
    """
    Parse the given string representation of an answer into an AnyAnswer.

    `mode` is a question type: chalk's own ("text", "repo") or an mdq type
    ("numeric", "multiple-selection"...). Unknown types read as plain text.
    """

    try:
        match mode:
            case "numeric":
                return _parse_numeric(answer)
            case "multiple-selection" | "ordering":
                return _parse_list(answer)
            case "true-false" | "fill-in":
                return _parse_dict(answer)
            case None:
                return _parse_any(answer)
            case _:
                return answer

    except ValueError as e:
        if error == "raise":
            raise e
        return answer


def _parse_numeric(answer: str, /) -> NumericAnswer:
    try:
        return int(answer)
    except ValueError:
        pass
    try:
        return float(answer)
    except ValueError:
        pass
    try:
        return Decimal(answer)
    except Exception:
        raise ValueError(f"Invalid numeric answer: {answer}")


def _parse_list(answer: str, /) -> ListAnswer:
    try:
        data = yaml.loads(answer)
    except Exception:
        raise ValueError(f"Invalid list answer: {answer}")
    if isinstance(data, list):
        return tuple(tuple(a) if isinstance(a, list) else a for a in data)
    raise ValueError(f"Invalid list answer: {answer}")


def _parse_dict(answer: str, /) -> MappingAnswer:
    try:
        data = yaml.loads(answer)
    except Exception:
        raise ValueError(f"Invalid dict answer: {answer}")
    if isinstance(data, dict) and all(isinstance(k, str) for k in data.keys()):
        return frozendict(data)
    raise ValueError(f"Invalid dict answer: {answer}")


def _parse_any(answer: str, /) -> AnyAnswer:
    try:
        return _parse_numeric(answer)
    except ValueError:
        pass
    try:
        return _parse_list(answer)
    except ValueError:
        pass
    try:
        return _parse_dict(answer)
    except ValueError:
        pass
    return answer
