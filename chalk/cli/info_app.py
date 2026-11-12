from typing import Annotated

import typer

from ..info import (
    display_debug_info,
    display_version_info,
    validate_info_format,
)
from .util import safe

__all__ = ["info", "add_info_command"]


def add_info_command(app: typer.Typer) -> None:
    app.command(no_args_is_help=False)(info)


@safe
def info(
    debug: Annotated[
        bool,
        typer.Option(
            ...,
            "-d",
            "--debug",
            help="Add the paths of the classroom and the environment.",
        ),
    ] = False,
    format: Annotated[
        str,
        typer.Option(
            ...,
            "-f",
            "--format",
            help="The output format (console, json, yaml).",
        ),
    ] = "console",
) -> None:
    """
    Show the version of chalk and of its main dependencies.

    The classroom and its quizzes are in `chalk show`.
    """
    if debug:
        display_debug_info(format=validate_info_format(format))
    else:
        display_version_info(format=validate_info_format(format))
