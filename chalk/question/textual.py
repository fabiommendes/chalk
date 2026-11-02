import re
from functools import lru_cache
from typing import Any, Iterable, override

import opt
from rich.console import RenderableType
from rich.syntax import Syntax

from ..core import models
from ..core.answer import TextualAnswer
from ..core.grader import Grader
from .base import (
    BaseQuestion,
    empty_result,
    validate_type,
)
from .renderable import RenderableField

# Mapping between formats and extensions when we diverge from pygments
FORMAT_EXTENSION_OVERRIDES = {
    "prolog": "pl",
}


class Textual(BaseQuestion[models.Textual, TextualAnswer]):
    """
    Textual questions have a text-based answer.

    It can be long essays or short answers and they can display text in many
    different forms like plain text, code snippets, mathematical formulas, etc.
    """

    @property
    def format(self) -> str:
        return self._conf.format or "text"

    @property
    def regex_validator(self) -> re.Pattern[str] | None:
        return self._conf.regex_validator

    @property
    def regex_grader(self) -> re.Pattern[str] | None:
        return self._conf.regex_grader

    @property
    def accepts_blank(self) -> bool:
        return self._conf.blank

    def get_answer_extension(self, default: str | None = None) -> str:
        suffix = suffix_from_format(self.format)
        return super().get_answer_extension(default=default or suffix)

    def render_answer(self, answer: TextualAnswer, plain: bool = False) -> RenderableType:
        """
        Render the question as a string.
        """
        if self.format is not None and self.format in syntax_highlight_formats() and not plain:
            return Syntax(
                answer,
                self.format,
                line_numbers=self.format != "text",
                theme="monokai",
                word_wrap=True,
            )
        else:
            return answer

    def get_grader(self) -> Grader[str] | None:
        if self.regex_grader is not None:
            from ..autograder.regex_grader import RegexGrader

            return RegexGrader(self.regex_grader, grade=self.value, match="search")

        script = self.get_autograde_script()
        if script is None:
            return None

        from ..autograder.script_grader import ScriptGrader

        return ScriptGrader(script=script, question=self, conf=self.get_autograder())

    def validate_answer(self, data: Any) -> TextualAnswer:
        answer = validate_type(data, str)
        if not self.accepts_blank and answer.strip() == "":
            raise empty_result()
        return answer

    @override
    def _render_base_fields(self, plain: bool = False) -> Iterable[tuple[str, RenderableField]]:
        yield from super()._render_base_fields(plain)
        yield "validator", opt.map(regex_fmt, self.regex_validator)
        yield "pattern", opt.map(regex_fmt, self.regex_grader)
        yield "format", self.format
        yield "accepts blank", self.accepts_blank


@lru_cache(1)
def syntax_highlight_formats() -> set[str]:
    from pygments.lexers import get_all_lexers

    lexers: set[str] = set()
    for _, short_names, _, _ in get_all_lexers():
        lexers.update(short_names)
    return lexers


@lru_cache(1)
def syntax_highlight_suffixes() -> dict[str, str]:
    from pygments.lexers import get_all_lexers

    mapping: dict[str, str] = {}
    for _, names, suffixes, _ in get_all_lexers():
        suffix = suffixes[0].removeprefix("*.") if suffixes else None
        if suffix is None:
            continue
        for name in names:
            mapping[name] = suffix
    mapping["text"] = "txt"
    mapping.update(FORMAT_EXTENSION_OVERRIDES)
    return mapping


def regex_fmt(pattern: re.Pattern[str]) -> str:
    """
    Format a regex pattern for display.
    """
    pat = pattern.pattern.replace("/", "\\/")
    return f"/{pat}/"


def suffix_from_format(fmt: str) -> str:
    """
    Get a suffix for the answer based on the format.
    """
    return syntax_highlight_suffixes().get(fmt, "txt")
