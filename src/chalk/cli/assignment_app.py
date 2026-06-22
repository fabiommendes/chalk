import datetime
import sys
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Iterable, Literal

import opt
import rich
import typer

from ..conf import find_project_root
from ..core import Grade, question
from ..core.assignment import Assignment, iter_assignments
from ..env import ask_optional_string
from ..table import Table, validate_table_format
from ..util.decimal import format_decimal, normalize_decimal
from .util import safe

app = typer.Typer(help="Manage the student roster.", no_args_is_help=True)


# ==============================================================================
# chalk assignment list
# ==============================================================================
@app.command(name="list")
@safe
def list_assignments(
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

    if not ids:
        rich.print("No assignment found!")
        return

    table = Table(rows, index=ids)
    table = table.select_columns(["name", "start", "end"])
    table.render(
        sort=sort,
        styles={"id": "bold yellow"},
    )


# ==============================================================================
# chalk assignment create ID
# ==============================================================================
@app.command(name="create")
@safe
def create(
    assignment_id: Annotated[
        str,
        typer.Argument(
            ...,
            help="Assignment identifier (e.g. 'hw1', 'exam1', etc.)",
        ),
    ],
    name: Annotated[
        str | None,
        typer.Option(
            ...,
            "-n",
            "--name",
            help="Assignment name",
        ),
    ] = None,
    questions: Annotated[
        list[str] | None,
        typer.Option(
            ...,
            "-q",
            "--questions",
            help="Number of questions or comma-separated list of question IDs",
        ),
    ] = None,
    start: Annotated[
        datetime.datetime | None,
        typer.Option(
            ...,
            "--start",
            help="Start date and time for the assignment (e.g. '2024-01-01 09:00')",
        ),
    ] = None,
    end: Annotated[
        datetime.datetime | None,
        typer.Option(
            ...,
            "--end",
            help="End date and time for the assignment (e.g. '2024-01-01 17:00')",
        ),
    ] = None,
    split: Annotated[
        bool,
        typer.Option(
            ...,
            "--split",
            help="Split the assignment into separate files (assignment.yaml, questions/, etc.)",
        ),
    ] = False,
    format: Annotated[
        Literal["csv", "json", "yaml", "xlsx"],
        typer.Option(
            ...,
            "--format",
            "-f",
            help="File format to save assignment in (csv, json, yaml, xlsx)",
        ),
    ] = "csv",
) -> None:
    """
    Create a new assignment.
    """

    for id, loader in iter_assignments():
        if id == assignment_id:
            rich.print("[b red]Assignment already exists[/]", file=sys.stderr)
            raise SystemExit(1)

        path = find_project_root() / "assignments" / f"{assignment_id}.{format}"
        if questions:
            if len(questions) == 1 and questions[0].isdigit():
                questions = [f"q{i + 1}" for i in range(int(questions[0]))]
            else:
                questions = [q.strip() for q in questions]

        assignment = Assignment(
            id=assignment_id,
            path=path,
            start=start,
            end=end,
            name=ask_optional_string(
                "Name",
                name,
                default=assignment_id,
            ),
            submissions={},
            questions={
                id: question.Generic(id=id, grade=Decimal(1)) for id in questions
            }
            if questions
            else None,
        )

        assignment.save(split=split)
        rich.print(assignment)


# ==============================================================================
# chalk assignment show ID
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
    Show details of an assignment.
    """
    assignment = Assignment.prompt(assignment_id)

    if not missing and not grades:
        assignment.dump(
            output_path,
            format=opt.map(validate_table_format, output_format),
        )
    elif grades:
        table = assignment.get_grades(total="total")
        table.dump(
            output_path,
            format=opt.map(validate_table_format, output_format),
            styles={"id": "bold yellow", "total": "bold"},
            sort=sort,
            last_row={
                "id": "mean",
                "total": render_mean(table.get_column("total")),
            },
        )
    elif missing:
        raise NotImplementedError("Missing submission report is not yet implemented")


# ==============================================================================
# chalk assignment merge ID1 ID2
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


#
# Utilities
#
def render_mean(data: Iterable[Decimal | Grade | None]) -> str | None:
    filtered = opt.filter(data)
    numbers = list(map(normalize_decimal, filtered))  # type: ignore
    if (n := len(numbers)) == 0:
        return None
    return format_decimal(sum(numbers, Decimal(0)) / n)
