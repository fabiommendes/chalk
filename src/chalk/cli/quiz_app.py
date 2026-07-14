import datetime
import sys
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Iterable

import opt
import rich
import typer

from ..core import Classroom, Grade, Quiz, models
from ..core.decimal import as_chalk_decimal, render_decimal
from ..env import ask_optional_string
from ..table import Table, validate_table_format
from .util import safe

app = typer.Typer(help="Manage the student roster.", no_args_is_help=True)


# ==============================================================================
# chalk quiz list
# ==============================================================================
@app.command(name="list")
@safe
def list_quizzes(
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
    Show the current list of quizzes.
    """

    if sort is not None and sort not in {"id", "name", "start", "end"}:
        rich.print(f"[b red]Invalid sort column: {sort}[/]", file=sys.stderr)
        raise typer.Exit(1)

    cfg = Classroom.load()
    rows = []
    ids: list[str] = []

    for quiz in cfg.iter_quizzes():
        cells = {
            "name": quiz.name,
            "start": quiz.start,
            "end": quiz.end,
        }

        ids.append(quiz.id)
        rows.append(cells)

    if not ids:
        rich.print("No quiz found!")
        return

    table = Table(rows, index=ids)
    table = table.select_columns(["name", "start", "end"])
    table.print(
        sort=sort,
        styles={"id": "bold yellow"},
    )


# ==============================================================================
# chalk quiz create ID
# ==============================================================================
@app.command(name="create")
@safe
def create(
    quiz_id: Annotated[
        str,
        typer.Argument(
            ...,
            help="Quiz identifier (e.g. 'hw1', 'exam1', etc.)",
        ),
    ],
    name: Annotated[
        str | None,
        typer.Option(
            ...,
            "-n",
            "--name",
            help="Quiz name",
        ),
    ] = None,
    question_ids: Annotated[
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
            help="Start date and time for the quiz (e.g. '2024-01-01 09:00')",
        ),
    ] = None,
    end: Annotated[
        datetime.datetime | None,
        typer.Option(
            ...,
            "--end",
            help="End date and time for the quiz (e.g. '2024-01-01 17:00')",
        ),
    ] = None,
) -> None:
    """
    Create a new quiz.
    """

    cls = Classroom.load()

    for quiz in cls.iter_quizzes():
        if quiz_id == quiz.id:
            rich.print("[b red]Quiz already exists[/]", file=sys.stderr)
            raise SystemExit(1)

    quiz_root = cls.root / quiz_id
    path = quiz_root / "conf.toml"

    if question_ids:
        if len(question_ids) == 1 and question_ids[0].isdigit():
            question_ids = [f"q{i + 1}" for i in range(int(question_ids[0]))]
        else:
            question_ids = [q.strip() for q in question_ids]

    conf = models.Quiz(
        start=start,
        end=end,
        name=ask_optional_string(
            "Name",
            name,
            default=quiz_id,
        ),
        questions=question_ids
        if question_ids is None
        else [models.GenericQuestion(id=id) for id in question_ids],
    )

    quiz = Quiz(quiz_id, conf, cls)
    quiz.save()
    rich.print(quiz)


# ==============================================================================
# chalk quiz show ID
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
    grades: Annotated[
        bool,
        typer.Option(
            ...,
            "-g",
            "--grades",
            help="Show all grades for the quiz.",
        ),
    ] = False,
    missing: Annotated[
        bool,
        typer.Option(
            ...,
            "-m",
            "--missing",
            help="Show which students have not submitted the quiz.",
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
    Show details of a quiz.
    """
    cfg = Classroom.load()
    quiz = cfg.prompt_quiz(quiz_id)

    if not missing and not grades:
        quiz.dump(
            output_path,
            format=opt.map(validate_table_format, output_format),
        )
    elif grades:
        table = Table.from_dataframe(quiz.grades.get_dataframe(total="total"))
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
# chalk quiz merge ID1 ID2
# ==============================================================================
@app.command(name="merge")
@safe
def merge(
    id1: Annotated[
        str,
        typer.Argument(
            ...,
            help="ID of the first quiz to merge",
        ),
    ],
    id2: Annotated[
        str,
        typer.Argument(
            ...,
            help="ID of the second quiz to merge",
        ),
    ],
    output_id: Annotated[
        str | None,
        typer.Option(
            ...,
            "-o",
            "--output",
            help="ID for the merged quiz (defaults to ID1)",
        ),
    ] = None,
) -> None:
    """
    Merge two quizzes into a single quiz file.

    This is useful for merging changes from different branches or collaborators.
    """
    cfg = Classroom.load()
    quiz1 = cfg.prompt_quiz(id1)
    quiz2 = cfg.prompt_quiz(id2)

    if output_id is None:
        output_id = id1 + "-merged"

    msg = f"Merging quizzes '{quiz1.name}' and '{quiz2.name}' into '{output_id}'..."
    print(msg)
    raise NotImplementedError("Quiz merging is not yet implemented")


#
# Utilities
#
def render_mean(data: Iterable[Decimal | Grade | None]) -> str | None:
    filtered = opt.filter(data)
    numbers = list(map(as_chalk_decimal, filtered))  # type: ignore
    if (n := len(numbers)) == 0:
        return None
    return render_decimal(sum(numbers, Decimal(0)) / n)
