import sys

import typer

from chalk_grader import cgroup

from . import (
    autograde_cmd,
    clear_app,
    codehood_app,
    contrib_app,
    grade_cmd,
    info_app,
    init_app,
    quiz_app,
    response_cmds,
    roster_app,
    show_cmd,
)

app = typer.Typer(name="Chalk", no_args_is_help=True, add_help_option=True)


NOT_GIVEN = object()
ADD_STUDENT_OPTIONS = {"email", "github", "name", "force"}

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
    codehood_app.app,
    name="codehood",
    help="Exchange data with a codehood course in the same repository.",
)
grade_cmd.add_grade_cmd(app)
autograde_cmd.add_autograde_command(app)
info_app.add_info_command(app)
contrib_app.add_contrib_command(app)
clear_app.add_clear_command(app)
show_cmd.add_show_command(app)
response_cmds.add_response_commands(app)


#: Commands that grade: they run again in a cgroup of their own, so that
#: each run gets a memory and process limit (see chalk_grader.cgroup).
GRADING_COMMANDS = (("autograde",), ("codehood", "autograde"))


def main() -> None:
    words = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    grading = any(tuple(words[: len(c)]) == c for c in GRADING_COMMANDS)
    if grading and "--help" not in sys.argv:
        cgroup.reexec_delegated()
        # Before the grader starts any process: the setup of the cgroups
        # gives up when the delegated cgroup has other processes.
        cgroup.controller()
    app()
