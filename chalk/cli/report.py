from typing import Annotated

import typer

from ..core import Classroom
from ..core.error import ChalkException
from ..table import Table, validate_table_format
from .util import safe

app = typer.Typer()


@app.command()
@safe
def grade(
    quiz_id: Annotated[
        str | None,
        typer.Option(
            ...,
            "-a",
            "--quiz",
            help="The quiz to grade",
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
    Show all grades for the given quiz and student.
    """
    cfg = Classroom.load()
    stream = open(output, "r") if output else None
    if quiz_id and student_id:
        raise NotImplementedError
    elif quiz_id:
        quiz = cfg.get_quiz(quiz_id)
        if quiz is None:
            raise ChalkException(f"Quiz {quiz_id} not found")

        grades = Table.from_dataframe(quiz.grades.get_dataframe(total="total"))
        grades.dump(
            stream,
            render={float: lambda g: f"{g:.2f}"},
            format=validate_table_format(format or "table"),
            sort=sort_by or "id",
        )
    elif student_id:
        student = cfg.get_student(student_id)
        if student is None:
            raise ChalkException(f"Student {student_id} not found")
        raise NotImplementedError
    else:
        raise NotImplementedError
