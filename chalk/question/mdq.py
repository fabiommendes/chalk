"""
Questions whose document is an mdq file in <quiz>/questions/.

The mdq document holds the stem, the choices and the answer key. The chalk
configuration (an entry in conf.yaml with the same id, optional) holds only
what is specific to chalk: value, autograder and answer suffix.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import mdq
import mdq.models as mdqm
from mdq.errors import NotAutoGradable, ResponseError
from rich.console import RenderableType
from rich.text import Text

from ..core import models
from ..core.answer import AnyAnswer, parse_any_answer
from ..core.grader import Graded, Grader
from ..core.models import QuestionId, StudentId
from .base import BaseQuestion, empty_result, fail
from .renderable import RenderableField

if TYPE_CHECKING:
    from ..core.quiz import Quiz

__all__ = ["MdqQuestion", "MDQ_SUFFIXES", "load_mdq_document", "mdq_question_id"]

#: Suffixes of question files, in order of precedence.
MDQ_SUFFIXES = (".mdq.md", ".md", ".mdq", ".yaml", ".yml", ".json")


class MdqQuestion(BaseQuestion[models.GenericQuestion, AnyAnswer]):
    """
    A question defined by an mdq document.

    Answers follow the response shapes of mdq (docs/responses.md): the id of
    a choice for multiple-choice, a list of ids for multiple-selection, a
    mapping of statement id to boolean for true-false, a number for numeric,
    text for short-answer and essay, and so on.
    """

    def __init__(
        self,
        id: QuestionId,
        conf: models.GenericQuestion,
        document: mdqm.Question,
        *,
        path: Path | None = None,
        quiz: Quiz,
    ):
        super().__init__(id, conf, quiz=quiz)
        self._document = document
        self._path = path

    @property
    def document(self) -> mdqm.Question:
        return self._document

    @property
    def path(self) -> Path | None:
        """
        Path of the mdq file that defines this question.
        """
        return self._path

    @property
    def type(self) -> str:  # type: ignore[override]
        return self._document.type

    @property
    def name(self) -> str:
        return self._conf.name or self._document.title or self.id

    @property
    def stem(self) -> str | None:
        return self._document.stem

    @property
    def value(self) -> Decimal:
        if self._conf.value is not None:
            return self._conf.value
        weight = getattr(self._document, "weight", None)
        return Decimal(str(weight)) if weight is not None else Decimal(1)

    @property
    def is_automatic(self) -> bool:
        """
        True if mdq grades every response to this question by itself.
        """
        return self._document.automation == "automatic"

    #
    # Answers
    #
    def validate_answer(self, answer: Any, /) -> AnyAnswer:
        response = self.to_response(answer)
        try:
            self._document.score_response(response)
        except ResponseError as e:
            raise fail("invalid-response", str(e)) from e
        except NotAutoGradable:
            pass
        return response

    def to_response(self, answer: Any, /) -> Any:
        """
        Convert an answer as chalk stores it (often a string read from a CSV
        cell) to the response mdq expects for this question type.
        """
        if answer is None or (isinstance(answer, str) and not answer.strip()):
            raise empty_result()

        match self.type:
            case "multiple-choice":
                return self._choice_id(answer)
            case "multiple-selection":
                if isinstance(answer, str):
                    answer = _split_list(answer)
                if not isinstance(answer, Sequence) or isinstance(answer, str):
                    raise fail("type-error", f"Expected a list of choices, got {answer!r}.")
                return [self._choice_id(item) for item in answer]
            case "numeric":
                if isinstance(answer, str):
                    return parse_any_answer(answer.strip(), mode="numeric", error="ignore")
                return answer
            case "short-answer" | "essay":
                return str(answer)
            case "true-false" | "fill-in":
                if isinstance(answer, str):
                    answer = parse_any_answer(answer, mode=None, error="ignore")
                if isinstance(answer, Mapping):
                    return dict(answer)
                return answer
            case "ordering":
                if isinstance(answer, str):
                    answer = parse_any_answer(answer, mode=None, error="ignore")
                if isinstance(answer, (list, tuple)):
                    return [list(item) if isinstance(item, tuple) else item for item in answer]
                return answer
            case _:
                return answer

    def _choice_id(self, answer: Any) -> Any:
        """
        Accept the id of a choice or, when no id matches, its exact text.
        """
        if not isinstance(answer, str):
            return answer
        answer = answer.strip()
        choices = getattr(self._document, "choices", None) or []
        ids = {choice.id for choice in choices}
        if answer in ids:
            return answer
        for choice in choices:
            if choice.text.strip() == answer:
                return choice.id
        return answer

    def render_answer(self, answer: Any, plain: bool = False) -> RenderableType:
        choices = getattr(self._document, "choices", None)
        if not choices:
            return super().render_answer(answer, plain=plain)

        texts = {choice.id: choice.text for choice in choices}
        selected = [answer] if isinstance(answer, str) else list(answer or ())
        return Text("\n".join(f"{id}: {texts.get(id, '?')}" for id in selected))

    #
    # Grading
    #
    def grade_answer(self, answer: Any, /) -> Graded | None:
        """
        Grade the answer with mdq. Return None for responses mdq leaves to
        the instructor (essays, unmatched short answers...).
        """
        try:
            result = self._document.score_response(self.to_response(answer))
        except NotAutoGradable:
            return None
        except ResponseError as e:
            raise fail("invalid-response", str(e)) from e

        feedback = "\n".join(result.feedback) or None
        return Graded(Decimal(str(result.score)), feedback=feedback)

    def get_grader(self) -> Grader[Any] | None:
        script = self.get_autograde_script()
        if script is not None:
            from ..autograder.script_grader import ScriptGrader

            return ScriptGrader(script=script, question=self, conf=self.get_autograder())

        def grader(id: StudentId, answer: Any, /, **kwargs: Any) -> Graded | None:
            return self.grade_answer(answer)

        return grader

    #
    # Rendering
    #
    def _render_base_fields(self, plain: bool = False) -> Iterable[tuple[str, RenderableField]]:
        yield from super()._render_base_fields(plain)
        if self._path is not None:
            yield "file", str(self._path.relative_to(self.quiz.root))

    def _render_base_sections(self, plain: bool = False) -> Iterable[RenderableType]:
        yield from super()._render_base_sections(plain)
        yield Text(self._document.render())


def mdq_question_id(path: Path) -> QuestionId | None:
    """
    Id of the question defined in the given file, or None if the file is not
    a question file.
    """
    name = path.name
    for suffix in MDQ_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name.removesuffix(suffix)
    return None


def load_mdq_document(path: Path, id: QuestionId) -> mdqm.Question:
    """
    Load and validate the mdq question in path.

    The document gets ids for all its choices, so responses can refer to
    them. Raises ValueError if the file is not a valid question or if it
    declares an id different from its file name.
    """
    loaded = mdq.load(path, kind="question", ids="fill")
    errors = [d for d in loaded.diagnostics if d.severity == "error"]
    if loaded.document is None or errors:
        details = "; ".join(_format_diagnostic(d) for d in errors) or "invalid question"
        raise ValueError(f"{path}: {details}")
    document = loaded.document

    if document.id is not None and document.id != id:
        raise ValueError(f"{path}: question id {document.id!r} does not match the file name {id!r}")
    if document.id is None:
        document = document.model_copy(update={"id": id})
    return document


def _format_diagnostic(diagnostic: mdq.Diagnostic) -> str:
    where = ".".join(map(str, diagnostic.path)) if diagnostic.path else ""
    if diagnostic.line is not None:
        where = f"line {diagnostic.line}" + (f" ({where})" if where else "")
    return f"{where}: {diagnostic.message}" if where else diagnostic.message


def _split_list(answer: str) -> list[str]:
    """
    Parse a list of choices written as YAML/JSON or as comma separated ids.
    """
    parsed = parse_any_answer(answer, mode="multiple-selection", error="ignore")
    if isinstance(parsed, tuple):
        return [str(item) for item in parsed]
    return [item.strip() for item in answer.split(",") if item.strip()]
