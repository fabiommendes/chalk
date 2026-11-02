from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeIs, assert_never, cast

from rich.console import Group, RenderableType
from rich.text import Text

if TYPE_CHECKING:
    from chalk.core import Quiz, models

from ..core.answer import AnyAnswer
from ..core.answer import serialize_any_answer as _serialize_answer
from .base import Generic
from .mdq import MdqQuestion
from .repo import Repo
from .textual import Textual

__all__ = (
    "Question",
    "Generic",
    "MdqQuestion",
    "Repo",
    "Textual",
)

Question = Generic | Textual | MdqQuestion | Repo


def load_question(id: models.QuestionId, conf: models.Question, /, quiz: Quiz) -> Question:
    """
    Load a question from its configuration model.
    """
    match conf.type:
        case None:
            return Generic(id, cast("models.GenericQuestion", conf), quiz=quiz)
        case "text":
            return Textual(id, conf, quiz=quiz)
        case "repo":
            return Repo(id, conf, quiz=quiz)
        case other:
            assert_never(other)
    raise ValueError(f"Unknown question type: {conf.type}")


def is_question(data: Any) -> TypeIs[Question]:
    """
    Check if the given data is a valid Question object.
    """
    return isinstance(data, Question)


def render_answer(
    question: Question, answer: AnyAnswer | None, /, *, plain: bool = False
) -> RenderableType:
    """
    Render the given answer for the specified question.
    """
    if answer is None:
        return Text("No answer provided", style="dim")
    try:
        validated: Any = question.validate_answer(answer)
        return question.render_answer(validated, plain=plain)
    except ValueError as e:
        return Group(Text("Invalid answer", style="bold red"), str(e))


def serialize_answer(
    question: Question,
    answer: AnyAnswer | None,
    /,
    *,
    error: Literal["raise", "ignore"] = "raise",
) -> str:
    """
    Serialize the given answer for the specified question.
    """
    if answer is None:
        return ""
    if error == "ignore" and isinstance(answer, str):
        return answer

    try:
        validated: Any = question.validate_answer(answer)
        return question.serialize_answer(validated)
    except ValueError:
        if error == "raise":
            raise
        elif error == "ignore":
            return _serialize_answer(answer)
        else:
            raise ValueError(f"Invalid error handling option: {error}")


def persist_answer(
    question: Question,
    student_id: str,
    answer: AnyAnswer | None,
    /,
    *,
    error: Literal["raise", "ignore"] = "raise",
    overwrite: bool = False,
) -> None:
    """
    Persist the given answer for the specified question and student.
    """
    if answer is None:
        return

    data = serialize_answer(question, answer, error=error)  # Validate the answer before persisting
    ext = question.get_answer_extension() or "txt"
    path = question.root / "responses" / f"{student_id}.{ext}"  # Persist the serialized answer

    if path.exists() and not overwrite:
        if error == "raise":
            raise FileExistsError(f"Answer file already exists: {path}")
        return

    path.write_text(data, encoding="utf-8")
