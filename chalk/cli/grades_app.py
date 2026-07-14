from pathlib import Path
from typing import Annotated, Iterable

import typer

from ..core import Classroom
from ..table import Table, validate_table_format
from .util import safe

__all__ = ["grades", "add_grades_command"]


def add_grades_command(app: typer.Typer) -> None:
    app.command(no_args_is_help=False)(grades)


@safe
def grades(
    quiz_id: Annotated[
        str | None,
        typer.Argument(
            metavar="ASSIGNMENT",
            help="Select a specific quiz to display information about.",
        ),
    ] = None,
    sort: Annotated[
        str,
        typer.Option(
            ...,
            "-s",
            "--sort",
            help="The sorting criteria for displaying grades.",
        ),
    ] = "id",
    format: Annotated[
        str,
        typer.Option(
            ...,
            "-f",
            "--format",
            help="The output format for displaying grades.",
        ),
    ] = "table",
    output_path: Annotated[
        Path | None,
        typer.Option(
            ...,
            "-o",
            "--output",
            help="The output file path for saving grades.",
        ),
    ] = None,
) -> None:
    """
    Display detailed information about a Chalk project.
    """
    cfg = Classroom.load()

    # Display table for single quiz
    if quiz_id:
        quiz = cfg.get_quiz(quiz_id)
        if quiz is None:
            raise SystemExit(f"Quiz {quiz_id} does not exist.")

        table = Table.from_dataframe(quiz.grades.get_dataframe(total=True))
        table.dump(
            output_path,
            format=validate_table_format(format),
            sort=sort,
        )
    else:
        df = cfg.get_grades()
        table = Table.from_dataframe(df)
        table.dump(
            output_path,
            format=validate_table_format(format),
            sort=sort,
        )


def next_of(name: str, names: Iterable[str]) -> str:
    """
    Get the next column name after the specified column in the list of columns.
    If the specified column is not found, return the last column in the list.
    """
    names = set(names)
    base = name
    idx = 0

    while name in names:
        idx += 1
        name = f"{base}-{idx}"
    return name
