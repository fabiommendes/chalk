import sys
from pathlib import Path
from typing import Annotated

import errorz as rz
import opt
import rich
import typer

from ..core import Assignment, SystemError
from ..table import Table, validate_table_format
from .util import read_assignment_and_question, safe

app = typer.Typer(help="Manage questions in assignments.", no_args_is_help=True)


# ==============================================================================
# chalk question list ASSIGNMENT
# ==============================================================================
@app.command(name="list")
@safe
def list_questions(
    assignment_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            help="Assignment identifier (e.g. 'hw1', 'exam1', etc.)",
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
    Show the current list of questions in the specified assignment.
    """
    assignment = Assignment.prompt(assignment_id)

    if sort is not None and sort not in {"id", "name", "type", "grade"}:
        rich.print(f"[b red]Invalid sort column: {sort}[/]", file=sys.stderr)
        raise typer.Exit(1)

    rows = []
    ids: list[str] = []
    for id, question in (questions := assignment.get_questions()).items():
        cells = {
            "name": question.name,
            "type": question.type,
            "grade": question.grade,
        }

        ids.append(id)
        rows.append(cells)
    total = (
        sum(
            question.grade
            for question in questions.values()
            if question.grade is not None
        )
        or None
    )

    table = Table(rows, index=ids)
    table = table.select_columns(["name", "type", "grade"])
    table.dump(
        output_path,
        sort=sort,
        styles={"id": "bold yellow"},
        last_row={"grade": total, "id": "total"},
        format=opt.map(validate_table_format, output_format),
    )


# ==============================================================================
# chalk question show ASSIGNMENT QUESTION
# ==============================================================================
@app.command(name="show")
@safe
def show(
    assignment_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            help="Assignment identifier (e.g. 'hw1', 'exam1', etc.)",
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
    Show details of an assignment.
    """
    _, question = read_assignment_and_question(assignment_id, question_id)

    question.display()


# ==============================================================================
# chalk question merge ASSIGNMENT QUESTION1 QUESTION2
# ==============================================================================
@app.command(name="merge")
@safe
def merge(
    id1: Annotated[
        str,
        typer.Argument(
            ...,
            help="ID of the first assignment to merge",
        ),
    ],
    id2: Annotated[
        str,
        typer.Argument(
            ...,
            help="ID of the second assignment to merge",
        ),
    ],
    output_id: Annotated[
        str | None,
        typer.Option(
            ...,
            "-o",
            "--output",
            help="ID for the merged assignment (defaults to ID1)",
        ),
    ] = None,
) -> None:
    """
    Merge two assignments into a single assignment file.

    This is useful for merging changes from different branches or collaborators.
    """
    assignment1 = Assignment.prompt(id1)
    assignment2 = Assignment.prompt(id2)

    if output_id is None:
        output_id = id1 + "-merged"

    msg = f"Merging assignments '{assignment1.name}' and '{assignment2.name}' into '{output_id}'..."
    print(msg)
    raise NotImplementedError("Assignment merging is not yet implemented")


# ==============================================================================
# chalk question convert ASSIGNMENT QUESTION
# ==============================================================================
@app.command()
@safe
def convert(
    assignment_id: Annotated[
        str | None,
        typer.Argument(metavar="ASSIGNMENT"),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(metavar="QUESTION"),
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
) -> None:
    """
    Show all grades for the given assignment and student.
    """

    assignment, question = read_assignment_and_question(assignment_id, question_id)

    if format:
        if question.type == format:
            msg = "Question is already in the desired format."
            typer.echo(msg)
            return
        if question.type is not None:
            msg = f"Cannot convert question of type {question.type} to {format}"
            raise SystemError.INVALID_FIELD(msg)

        responses = assignment.get_responses_for_question(question.id)
        rich.print(responses)


# ==============================================================================
# chalk question issues ASSIGNMENT QUESTION
# ==============================================================================
@app.command()
@safe
def issues(
    assignment_id: Annotated[
        str | None,
        typer.Argument(metavar="ASSIGNMENT"),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(metavar="QUESTION"),
    ] = None,
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
    fix: Annotated[
        bool,
        typer.Option(
            ...,
            "--fix",
            help="Automatically fix issues if possible (e.g. by inferring missing choices from responses)",
        ),
    ] = False,
) -> None:
    """
    Show all issues for the given question.
    """

    assignment, question = read_assignment_and_question(assignment_id, question_id)
    result = question.validate_question_with_responses(question.get_responses())
    responses = question.validate_responses(question.get_responses(), inplace=fix)

    issues = [
        issue
        for issues in responses.values()
        if rz.is_err(issues)
        for issue in issues.error
    ]

    if rz.is_err(result):
        issues.extend(result.error)

    if issues:
        for issue in sorted(set(issues)):
            issue.display()
            print()

    if not issues:
        rich.print("No issues found with this question 🥳.")
    elif fix:
        assignment.save()
