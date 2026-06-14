import builtins
from typing import Any

import rich
import typer

from . import (
    assignment_app,
    autograde_app,
    info_app,
    init_app,
    question_app,
    response_app,
    roster_app,
)
from . import report as report_app

app = typer.Typer(name="Chalk", no_args_is_help=True, add_help_option=True)

ADD_STUDENT_OPTIONS = {"email", "github", "name", "force"}
ADD_SIMPLE_ASSIGNMENT_OPTIONS = {
    "name",
    "start",
    "end",
    "questions",
    "format",
    "split",
    "force",
}

app.add_typer(
    init_app.app,
    name="init",
    help="Initialize a new Chalk project.",
)
app.add_typer(
    roster_app.app,
    name="roster",
    help="Manage the student roster.",
)
app.add_typer(
    assignment_app.app,
    name="assignment",
    help="Manage assignments.",
)
app.add_typer(
    question_app.app,
    name="question",
    help="Manage questions for assignments.",
)
app.add_typer(
    response_app.app,
    name="response",
    help="Manage responses for questions.",
)
app.add_typer(
    autograde_app.app,
    name="autograde",
    help="Manage autograder scripts and run autograding.",
)
app.add_typer(
    report_app.app,
    name="report",
    help="Generate reports for assignments and students.",
)
info_app.add_info_command(app)


def main() -> None:
    app()


def _add_debug_builtins() -> None:
    """
    Add a debug function to builtins for easier debugging in the CLI.
    This allows you to call `debug()` from anywhere in the CLI code to print
    debug information without needing to import anything.
    """

    def dbg(obj_or_name: Any, /, *args: Any, deep: bool = False) -> None:
        if args:
            rich.print(f"[red on white]{obj_or_name}[/]", end="")
        else:
            args = (obj_or_name,)

        if deep:
            for obj in args:
                rich.inspect(obj)
        else:
            rich.print(*args)

    builtins.dbg = dbg  # type: ignore


_add_debug_builtins()
