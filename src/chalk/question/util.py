from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Callable,
)

import errorz as rz

from ..types import QuestionId

if TYPE_CHECKING:
    from . import Question
    from .base import BaseQuestion


def question_id(question: Question | QuestionId) -> QuestionId:
    return question.id if isinstance(question, BaseQuestion) else question


def merge_errors[K, V, E](
    fn: Callable[[E, E], E],
    data1: dict[K, rz.Result[V, E]],
    data2: dict[K, rz.Result[V, E]],
    /,
) -> dict[K, rz.Result[V, E]]:
    """
    Merge two dictionaries of results, combining errors for matching keys.

    If both matching keys are correct, return the second.

    If both matching keys are errors, combine the errors into a single list.
    """
    merged: dict[K, rz.Result[V, E]] = dict(data1)
    for key, value in data2.items():
        try:
            other = merged[key]
        except KeyError:
            merged[key] = value
            continue

        match (other, value):
            case (rz.Err(e1), rz.Err(e2)):
                merged[key] = rz.err(fn(e1, e2))
            case (_, rz.Err(err)) | (rz.Err(err), _):
                merged[key] = rz.err(err)
            case (_, b):
                merged[key] = b
            case _:
                raise RuntimeError("Unreachable")

    return merged
