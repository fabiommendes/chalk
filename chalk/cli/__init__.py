import builtins
import inspect
from typing import Any

import opt
import rich
import typer

from . import (
    autograde_cmd,
    clear_app,
    collect_cmd,
    contrib_app,
    grade_cmd,
    info_app,
    init_app,
    plagiarism_app,
    question_app,
    quiz_app,
    response_cmds,
    roster_app,
    show_cmd,
)

app = typer.Typer(name="Chalk", no_args_is_help=True, add_help_option=True)


NOT_GIVEN = object()
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

init_app.add_init_command(app)
app.add_typer(
    roster_app.app,
    name="roster",
    help="Manage the student roster.",
)
app.add_typer(
    quiz_app.app,
    name="quiz",
    help="Manage quizzes.",
)
app.add_typer(
    question_app.app,
    name="question",
    help="Manage questions for quizzes.",
)
app.add_typer(
    plagiarism_app.app,
    name="plagiarism",
    help="Manage plagiarism detection and reports.",
)
collect_cmd.add_collect_command(app)
grade_cmd.add_grade_cmd(app)
autograde_cmd.add_autograde_command(app)
info_app.add_info_command(app)
contrib_app.add_contrib_command(app)
clear_app.add_clear_command(app)
show_cmd.add_show_command(app)
response_cmds.add_response_commands(app)


def main() -> None:
    app()


def _add_debug_builtins() -> None:
    """
    Add a debug function to builtins for easier debugging in the CLI.
    This allows you to call `debug()` from anywhere in the CLI code to print
    debug information without needing to import anything.
    """

    def dbg(obj_or_name: Any = NOT_GIVEN, /, *args: Any, deep: bool = False) -> None:
        if obj_or_name is NOT_GIVEN:
            frame = inspect.currentframe()
            frame = opt.map(lambda x: x.f_back, frame)
            if frame is None:
                rich.print("[red on white]dbg() called outside of a frame[/]")
                return

            rich.print(frame.f_locals)
            return

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
