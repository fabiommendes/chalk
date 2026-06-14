import sys
from pathlib import Path
from typing import Annotated

import rich
import typer

from .. import assets, env
from ..conf import is_project_root
from .util import safe

__all__ = ["app", "init"]


app = typer.Typer(name="chalk-init", no_args_is_help=True, add_help_option=True)


@app.command()
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
            "-t",
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
        roster.write_text("id,name")
    if not (assignments := base / "assignments").exists():
        assignments.mkdir()
    if not (reports := base / "reports").exists():
        reports.mkdir()
    if not (scripts := base / "scripts").exists():
        scripts.mkdir()
