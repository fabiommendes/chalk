from typing import Annotated

import typer

from ..core.assignment import _read_assignment_by_id
from ..table import validate_table_format
from .util import safe

app = typer.Typer()


@app.command()
@safe
def grade(
    assignment_id: Annotated[
        str | None,
        typer.Option(
            ...,
            "-a",
            "--assignment",
            help="The assignment to grade",
        ),
    ] = None,
    student_id: Annotated[
        str | None,
        typer.Option(
            ...,
            "-s",
            "--student",
            help="The student to grade",
        ),
    ] = None,
    format: Annotated[
        str | None,
        typer.Option(
            ...,
            "-f",
            "--format",
            help="The output format (table, csv, json)",
        ),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option(
            ...,
            "-o",
            "--output",
            help="The output file (defaults to stdout)",
        ),
    ] = None,
    sort_by: Annotated[
        str | None,
        typer.Option(
            ...,
            "-sc",
            "--sort-by",
            help="The column to sort by",
        ),
    ] = None,
) -> None:
    """
    Show all grades for the given assignment and student.
    """
    stream = open(output, "r") if output else None
    if assignment_id and student_id:
        raise NotImplementedError
    elif assignment_id:
        assignment = _read_assignment_by_id(assignment_id)
        grades = assignment.get_grades(total="total")
        grades.dump(
            stream,
            render={float: lambda g: f"{g:.2f}"},
            format=validate_table_format(format or "table"),
            sort=sort_by or "id",
        )
    elif student_id:
        raise NotImplementedError
    else:
        raise NotImplementedError
