from pathlib import Path
from typing import Annotated

import opt
import typer

from ..core import Classroom
from ..core.answer import serialize_any_answer
from ..data import (
    dump_data,
    dump_spreadsheet,
    dump_structured_data,
    is_spreadsheet_format,
    is_structured_format,
)
from ..table import Table
from .util import safe

__all__ = ["collect", "add_collect_command"]


def add_collect_command(app: typer.Typer) -> None:
    app.command(no_args_is_help=False)(collect)


@safe
def collect(
    loc: Annotated[
        str | None,
        typer.Argument(
            metavar="LOC",
            help="Quiz/question.",
        ),
    ] = None,
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file.",
        ),
    ] = None,
    color: Annotated[
        str,
        typer.Option(
            ...,
            "--color",
            metavar="CHOICE",
            help="Control rich text formatting. Options: 'auto', 'yes', 'no'.",
        ),
    ] = "auto",
) -> None:
    """
    Collect all responses for a question and save them in a single file.
    """
    cls, quiz, question = Classroom.from_prompt(loc, check_exist=True)
    answers = dict(quiz.submissions.iter_answers(question=question))

    if format is None and output is not None:
        format = output.suffix.removeprefix(".")
    if format is None:
        format = "yaml"

    if is_structured_format(format):
        dump_structured_data(answers, output, format=format)
        return

    if is_spreadsheet_format(format):
        table = Table(
            [
                {"id": id, "answer": opt.map(serialize_any_answer, answer)}
                for id, answer in answers.items()
            ]
        )
        dump_spreadsheet(table, output, format=format)
        return

    if format in ("md", "markdown", "txt", "text"):
        parts = []
        for student_id, answer in answers.items():
            parts.append(f"## {student_id}\n")
            parts.append(serialize_any_answer(answer))
            parts.append("---")

        if parts:
            parts.pop()
        src = "\n".join(parts)

        dump_data(src, output, format=format, word_wrap=True)
        return

    raise typer.BadParameter(f"Unsupported format: {format}", param_hint="--format")
