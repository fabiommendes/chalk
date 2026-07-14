import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Annotated
from weakref import proxy

import rich
import typer
from rich.prompt import Prompt

from chalk.core import Classroom

from .. import env
from .. import table as tb
from ..core import Quiz, Student, StudentId
from ..core.roster import ConflictMode, Roster, read_roster_like
from ..util import clean_data
from .util import safe

app = typer.Typer(help="Manage the student roster.", no_args_is_help=True)


# ==============================================================================
# chalk roster show
# ==============================================================================
@app.command(name="show")
@safe
def show(
    sort: Annotated[
        str,
        typer.Option(
            ...,
            "-s",
            "--sort",
            help="Sort by id, name, email, or github",
            metavar="COLUMN",
        ),
    ] = "id",
    format: Annotated[
        str,
        typer.Option(
            ...,
            "-f",
            "--format",
            help="Output format (table, csv, json, yaml)",
            metavar="FORMAT",
        ),
    ] = "table",
    output: Annotated[
        Path | None,
        typer.Option(
            ...,
            "-o",
            "--output",
            help="Write output to file",
            metavar="FILE",
        ),
    ] = None,
) -> None:
    """
    Show the current student roster.
    """

    cls = Classroom.load()
    roster = cls.get_roster()
    table = roster.table()

    reverse = False
    if isinstance(sort, str):
        if sort.startswith("-"):
            sort = sort[1:]
            reverse = True
        if sort.startswith("+"):
            sort = sort[1:]

    if sort and sort != "id" and sort not in table.columns:
        rich.print(f"[b red]Invalid sort column: {sort}[/]", file=sys.stderr)
        raise SystemExit(1)

    table.dump(
        output,
        format=tb.validate_table_format(format),
        styles={"email": "dim white", "id": "bold yellow"},
        sort=sort or "id",
        reverse=reverse,
    )


# ==============================================================================
# chalk roster add
# ==============================================================================
@app.command()
@safe
def add(
    student_id: Annotated[
        str | None,
        typer.Argument(help="Student identifier"),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option(
            ...,
            "-n",
            "--name",
            help="Student name",
        ),
    ] = None,
    email: Annotated[
        str | None,
        typer.Option(
            ...,
            "-e",
            "--email",
            help="Student email",
        ),
    ] = None,
    github: Annotated[
        str | None,
        typer.Option(
            ...,
            "-g",
            "--github",
            help="Student GitHub username",
        ),
    ] = None,
    email_alt: Annotated[
        str | None,
        typer.Option(
            ...,
            "--email-alt",
            help="Alternative student email",
        ),
    ] = None,
) -> None:
    """
    Add one student to the roster.
    """
    cls = Classroom.load()
    roster = cls.get_roster()
    if student_id is not None:
        student = Student(
            id=student_id,
            name=env.ask_optional_string("Name", name, default=student_id),
            classroom=proxy(cls),
            **clean_data(
                {
                    "email": env.ask_optional_string("Email", email),
                    "email_alt": env.ask_optional_string("Alternative email", email_alt), 
                    "github": env.ask_optional_string("GitHub", github),
                }
            ),
        )  # fmt: skip
        roster.add_students([student])
        return

    # Loop adding students until interrupted
    while True:
        student_id = Prompt.ask(
            "[bold yellow]Student ID [dim](leave blank to finish)[/][/]",
            default="",
            show_default=False,
        )
        if not student_id:
            break

        student = Student(
            id=student_id,
            name=env.ask_optional_string("Name", name, default=student_id),
            classroom=proxy(cls),
            **clean_data(
                {
                    "email": env.ask_optional_string("Email", email),
                    "email_alt": env.ask_optional_string("Alternative email", email_alt),
                    "github": env.ask_optional_string("GitHub", github),
                }
            ),
        )
        roster.add_students([student])
        print()


# ==============================================================================
# chalk roster import
# ==============================================================================
@app.command(name="import")
@safe
def import_roster(
    path: Annotated[
        Path,
        typer.Argument(help="Path to a roster-like file"),
    ],
    replace: Annotated[
        bool,
        typer.Option(
            ...,
            "-r",
            "--replace",
            help="Replace the current roster",
        ),
    ] = False,
    keep: Annotated[
        bool,
        typer.Option(
            ...,
            "-k",
            "--keep",
            help="Keep existing students on conflicts",
        ),
    ] = False,
) -> None:
    """
    Import roster data from an external file.
    """

    if replace and keep:
        raise SystemExit("Cannot use --replace and --keep together")

    cls = Classroom.load()
    imported = read_roster_like(path, cls)
    existing = cls.get_roster()
    students = list(imported.data.values())

    mode: ConflictMode = "replace" if replace else "keep" if keep else "merge"
    existing.add_students(students, conflict=mode)
    existing.save()


@app.command()
@safe
def validate(
    id: Annotated[
        str | None,
        typer.Option(
            ...,
            "--id",
            metavar="REGEX",
            help="Regular expression for valid student ids",
        ),
    ] = None,
    fields: Annotated[
        str | None,
        typer.Option(
            ...,
            "-f",
            "--fields",
            help="Comma-separated required fields",
        ),
    ] = None,
    quiz_id: Annotated[
        str | None,
        typer.Option(
            ...,
            "-a",
            "--quiz",
            metavar="ASSIGNMENT",
            help="Validate that all students have submissions for the specified quiz",
        ),
    ] = None,
    yes: Annotated[
        bool | None,
        typer.Option(
            ...,
            "--yes/--no",
            help="Automatically answer yes or no to all prompts during validation",
        ),
    ] = None,
) -> None:
    """Validate roster data for consistency and completeness."""

    cls = Classroom.load()
    roster = cls.get_roster()

    # If yes/no is set, but no other option is provided.
    if not id and not fields and not quiz_id:
        rich.print(
            "[b red]Nothing to validate! Use --id, --fields, or --quiz.[/]",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if id:
        validate_ids(roster, id, force_remove=yes)

    if fields:
        field_list = {field.strip() for field in fields.split(",") if field.strip()}
        validate_fields(roster, field_list)

    if quiz_id:
        quiz = cls.get_quiz(quiz_id)
        if quiz is None:
            raise SystemExit(f"[b red]Quiz {quiz_id} not found in classroom[/]")
        validate_quiz(roster, quiz)


def validate_ids(roster: Roster, pattern: str, force_remove: bool | None = None) -> None:
    id_pattern = re.compile(pattern)
    invalid_ids = [
        student.id for student in roster.data.values() if not id_pattern.fullmatch(student.id)
    ]

    if not invalid_ids:
        return

    # Show errors
    rich.print("[b red]Invalid student IDs:[/]", file=sys.stderr)
    for line in invalid_ids:
        rich.print(f"- [bold]{line}[/]", file=sys.stderr)

    # Ask for some action
    if force_remove is not None:
        action = "all" if force_remove else "none"
    else:
        action = Prompt.ask("Remove them?", choices=["ask", "all", "none"], default="ask")

    # Perform action
    if action == "ask":
        for student_id in invalid_ids:
            student = roster[student_id]
            remove = Prompt.ask(
                f"Remove [bold]{student_id}[/] ({student.name})?",
                choices=["y", "n"],
                default="n",
            )
            if remove == "y":
                del roster.data[student_id]
        roster.save()
    elif action == "all":
        for student_id in invalid_ids:
            del roster.data[student_id]
        roster.save()
    else:
        raise SystemExit(1)


def validate_fields(roster: Roster, fields: set[str]) -> None:
    errors: dict[StudentId, set[str]] = defaultdict(set)

    for student in roster.data.values():
        for field in fields:
            if getattr(student, field) in {None, ""}:
                errors[student.id].add(field)

    if errors:
        for student_id, missing_fields in errors.items():
            student = roster[student_id]
            rich.print(f"[b red]{student_id}[/] ({student.name})")
            for field in missing_fields:
                rich.print(f"  - missing: {field}")

        raise SystemExit(1)


def validate_quiz(roster: Roster, quiz: Quiz) -> None:
    submissions = quiz.submissions
    student_ids = set(roster.data.keys())

    missing = student_ids - submissions
    extra = submissions - student_ids

    if missing:
        rich.print(f"Missing submissions for [b red]{quiz.id}[/]")
        for student_id in missing:
            student = roster[student_id]
            rich.print(f"- [bold]{student_id}[/] ({student.name})")

    if extra:
        rich.print(f"Submissions from unknown students for [b red]{quiz.id}[/]")
        for student_id in extra:
            rich.print(f"- [bold]{student_id}[/]")

        prompt = Prompt.ask(
            "Add these students to the roster?",
            choices=["y", "n"],
            default="n",
        )
        if prompt == "y":
            for student_id in extra:
                roster.data[student_id] = Student(
                    id=student_id,
                    name="auto",
                    classroom=quiz.classroom,
                )
            roster.save()

    if missing or extra:
        raise SystemExit(1)
