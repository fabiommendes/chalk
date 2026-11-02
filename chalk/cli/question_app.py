import sys
from pathlib import Path
from typing import Annotated

import opt
import rich
import typer

from ..core import Classroom
from ..table import Table, validate_table_format
from .util import safe

app = typer.Typer(help="Manage questions in quizzes.", no_args_is_help=True)


# ==============================================================================
# chalk question list ASSIGNMENT
# ==============================================================================
@app.command(name="list")
@safe
def list_questions(
    quiz_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            help="Quiz identifier (e.g. 'hw1', 'exam1', etc.)",
        ),
    ] = None,
    sort: Annotated[
        str,
        typer.Option(
            ...,
            "-s",
            "--sort",
            help="Sort by id, name, start, or end",
            metavar="COLUMN",
        ),
    ] = "id",
    output_format: Annotated[
        str | None,
        typer.Option(
            ...,
            "-f",
            "--format",
            metavar="FORMAT",
            help="Specify the output format (e.g. 'table', 'json', etc.)",
        ),
    ] = None,
    output_path: Annotated[
        Path | None,
        typer.Option(
            ...,
            "-o",
            "--output",
            metavar="PATH",
            help="Specify a file to save the output to",
        ),
    ] = None,
) -> None:
    """
    Show the current list of questions in the specified quiz.
    """
    cfg, quiz = Classroom.from_prompt(quiz_id=quiz_id)

    if sort is not None and sort not in {"id", "name", "type", "grade"}:
        rich.print(f"[b red]Invalid sort column: {sort}[/]", file=sys.stderr)
        raise typer.Exit(1)

    rows = []
    ids: list[str] = []
    for id, question in (questions := quiz.get_questions()).items():
        cells = {
            "name": question.name,
            "type": question.type,
            "grade": question.value,
        }

        ids.append(id)
        rows.append(cells)
    total = sum(question.value for question in questions.values()) or None

    table = Table(rows, index=ids)
    table = table.select_columns(["name", "type", "grade"])
    table.dump(
        output_path,
        sort=sort,
        styles={"id": "bold yellow"},
        extra_rows=[{"grade": total, "id": "total"}],
        format=opt.map(validate_table_format, output_format),
    )


# ==============================================================================
# chalk question show ASSIGNMENT QUESTION
# ==============================================================================
@app.command(name="show")
@safe
def show(
    quiz_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            help="Quiz identifier (e.g. 'hw1', 'exam1', etc.)",
        ),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            metavar="QUESTION",
            help="Question identifier (e.g. 'q1', 'q2', etc.)",
        ),
    ] = None,
    grades: Annotated[
        bool,
        typer.Option(
            ...,
            "-g",
            "--grades",
            help="Show all grades and grading details for this question.",
        ),
    ] = False,
) -> None:
    """
    Show details of a question.
    """
    Classroom.from_prompt(quiz_id=quiz_id, question_id=question_id).question.render()
