import re
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any, Literal

import errorz as rz
import opt
from pydantic import BeforeValidator, PlainSerializer
from rich.console import Console
from rich.syntax import Syntax

from ..autograder import autograder_scripts
from ..core.grader import Grader
from ..data import serializers as s
from ..data import validators as v
from ..types import Answer
from ..util.show import display_field
from .base import (
    BaseQuestion,
    Issue,
    empty_issue,
    validate_type,
)

one = Decimal(1)
zero = Decimal(0)


class Textual(BaseQuestion[str]):
    """
    Textual questions have a text-based answer.

    It can be long essays or short answers and they can display text in many
    different forms like plain text, code snippets, mathematical formulas, etc.
    """

    type: Literal["text"] = "text"  # pyright: ignore[reportIncompatibleVariableOverride]
    format: Annotated[str | None, BeforeValidator(v.optional(v.text_format))] = None
    regex_validator: Annotated[
        re.Pattern[str] | None,
        BeforeValidator(v.optional(v.regex)),
        PlainSerializer(s.optional(s.regex)),
    ] = None
    regex_grader: Annotated[
        re.Pattern[str] | None,
        BeforeValidator(v.optional(v.regex)),
        PlainSerializer(s.optional(s.regex)),
    ] = None
    accepts_blank: bool = False

    def display_answer(self, answer: Any, rich: bool = True) -> None:
        """
        Render the question as a string.
        """
        if (
            self.format is not None
            and self.format in syntax_highlight_formats()
            and rich
        ):
            syntax = Syntax(answer, self.format, line_numbers=True, theme="monokai")
            Console().print(syntax)
        else:
            super().display_answer(answer, rich)

    def get_grader(self) -> rz.Result[Grader[str], str]:
        if self.regex_grader is not None:
            from ..autograder.regex_grader import RegexGrader

            return RegexGrader(
                self.regex_grader,
                grade=self.grade or one,
                match="search",
            )

        root = self.get_root_path()
        match autograder_scripts(root):
            case [script]:
                from ..autograder.script_grader import ScriptGrader

                return ScriptGrader(
                    root,
                    script=script,
                    grade=self.grade or one,
                    question_id=self.id,
                    assignment_id=opt.unwrap(self._assignment).id,
                )
            case []:
                return rz.err("No autograder or regex pattern found.")
            case _:
                return rz.err("Multiple autograder scripts are not supported yet.")

    def validate_answer(self, answer: Answer) -> rz.Result[str, list[Issue]]:
        if rz.is_err(val := validate_type(answer, str)):
            return val
        if not self.accepts_blank and val.strip() == "":
            return empty_issue()
        return rz.ok(val)

    def display(self, rich: bool = True) -> None:
        super().display(rich=rich)
        display_field("validator", opt.map(regex_fmt, self.regex_validator), rich=rich)
        display_field("pattern", opt.map(regex_fmt, self.regex_grader), rich=rich)
        display_field("format", self.format, rich=rich)
        display_field("accepts blank", self.accepts_blank, rich=rich)


@lru_cache(1)
def syntax_highlight_formats() -> set[str]:
    from pygments.lexers import get_all_lexers

    lexers: set[str] = set()
    for _, short_names, _, _ in get_all_lexers():
        lexers.update(short_names)
    return lexers


def regex_fmt(pattern: re.Pattern[str]) -> str:
    """
    Format a regex pattern for display.
    """
    pat = pattern.pattern.replace("/", "\\/")
    return f"/{pat}/"
