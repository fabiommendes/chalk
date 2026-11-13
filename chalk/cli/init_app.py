import sys
from pathlib import Path
from typing import Annotated

import rich
import typer

from .. import assets, env
from ..codehood import add_codehoodignore
from ..core.classroom import is_project_root
from ..core.roster import SHARED_COLUMNS
from .util import safe

__all__ = ["init", "add_init_command"]


def add_init_command(app: typer.Typer) -> None:
    app.command(no_args_is_help=False)(init)


@safe
def init(
    classroom: Annotated[
        str | None,
        typer.Option(
            ...,
            "-c",
            "--classroom",
            help="Classroom name",
        ),
    ] = None,
    teacher: Annotated[
        str | None,
        typer.Option(
            ...,
            "--teacher",
            help="Teacher's name",
        ),
    ] = None,
) -> None:
    """
    Initialize a new Chalk project.
    """
    if is_project_root(Path.cwd()):
        msg = "[b red]Chalk project already initialized in this directory[/]"
        rich.print(msg, file=sys.stderr)
        raise SystemExit(1)

    classroom = env.get_env_classroom(classroom, interactive=True)
    teacher = env.get_env_teacher(teacher, interactive=True)
    chalk_toml = assets.create_chalk_toml(teacher=teacher, classroom=classroom)

    # Write files
    base = Path.cwd()
    (base / "chalk.toml").write_text(chalk_toml)
    if not (roster := base / "roster.csv").exists():
        roster.write_text(",".join(SHARED_COLUMNS) + "\n")

    for dir in ["reports", "data", "scripts"]:
        if not (path := base / dir).exists():
            path.mkdir()

    if add_codehoodignore(base, "chalk.toml"):
        rich.print("Updated .codehoodignore")
