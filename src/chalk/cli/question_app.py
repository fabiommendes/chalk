import sys
from pathlib import Path
from typing import Annotated, Counter

import opt
import rich
import typer
from rich.padding import Padding

from ..core import Assignment, SystemError, iter_assignments
from ..data import dump_structured_data, validate_structured_format
from ..table import Table
from ..util.string import pluralize, truncate_lines
from .util import read_assignment_and_question, safe

app = typer.Typer(help="Manage questions in assignments.", no_args_is_help=True)


# ==============================================================================
# chalk question list ASSIGNMENT
# ==============================================================================
@app.command(name="list")
@safe
def list_assignments(
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
) -> None:
    """
    Show the current list of assignments.
    """
    assignment = Assignment.prompt(assignment_id)

    if sort is not None and sort not in {"id", "name", "start", "end"}:
        rich.print(f"[b red]Invalid sort column: {sort}[/]", file=sys.stderr)
        raise typer.Exit(1)

    rows = []
    ids: list[str] = []
    for id, loader in iter_assignments():
        try:
            assignment = loader()
        except Exception as e:
            rich.print(
                f"[b red]Error loading assignment {id}:[/]\n  [red]{e}[/]",
                file=sys.stderr,
            )
            continue

        cells = {
            "name": assignment.name,
            "start": assignment.start,
            "end": assignment.end,
        }

        ids.append(id)
        rows.append(cells)

    table = Table(rows, index=ids)
    table = table.select_columns(["name", "start", "end"])
    table.render(
        sort=sort,
        styles={"id": "bold yellow"},
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
    grades: Annotated[
        bool,
        typer.Option(
            ...,
            "-g",
            "--grades",
            help="Show all grades for the assignment.",
        ),
    ] = False,
    missing: Annotated[
        bool,
        typer.Option(
            ...,
            "-m",
            "--missing",
            help="Show which students have not submitted the assignment.",
        ),
    ] = False,
) -> None:
    """
    Show details of an assignment.
    """
    assignment = Assignment.prompt(assignment_id)

    if not missing and not grades:
        assignment.display()
    elif grades:
        table = assignment.get_grades(total=True)
        table.render(sort="id")
    elif missing:
        # TODO: Implement missing submission report
        raise NotImplementedError("Missing submissions report is not yet implemented")


# ==============================================================================
# chalk question choices ASSIGNMENT QUESTION
# ==============================================================================
@app.command()
@safe
def choices(
    assignment_id: Annotated[
        str | None,
        typer.Argument(
            metavar="ASSIGNMENT",
        ),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(
            metavar="QUESTION",
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
        Path | None,
        typer.Option(
            "-o",
            "--output",
            help="Output file path",
        ),
    ] = None,
) -> None:
    """
    List all choices for the given question.
    """

    assignment, question = read_assignment_and_question(assignment_id, question_id)
    responses = assignment.get_responses_for_question(question.id)
    choices = Counter([r.answer for r in responses.values() if r.answer is not None])
    frequencies = [
        {"choice": choice, "count": count} for choice, count in choices.most_common()
    ]

    if format or output:
        dump_structured_data(
            frequencies,
            output,
            format=opt.map(validate_structured_format, format),
        )
    else:
        for i, item in enumerate(frequencies):
            n = item["count"]
            source = truncate_lines(item["choice"], 8)
            rich.print(f"[b white]Choice {i + 1}:[/]")
            rich.print(Padding(source, (0, 0, 0, 2)))
            rich.print(f"  [dim]{n} {pluralize(n, 'occurrence')}[/]\n")

        msg = f"[b]Found {len(responses)} responses with {len(frequencies)} unique choices[/]"
        rich.print(msg)


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
    assignment_id: Annotated[str | None, typer.Argument(metavar="ASSIGNMENT")] = None,
    question_id: Annotated[str | None, typer.Argument(metavar="QUESTION")] = None,
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
