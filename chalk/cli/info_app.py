from typing import Annotated

import typer

from ..info import (
    display_debug_info,
    display_project_info,
    display_version_info,
    validate_info_format,
)
from .util import safe

__all__ = ["info", "add_info_command"]


def add_info_command(app: typer.Typer) -> None:
    app.command(no_args_is_help=False)(info)


@safe
def info(
    classroom: Annotated[
        bool,
        typer.Option(
            ...,
            "-c",
            "--classroom",
            help="Show classroom information.",
        ),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option(
            ...,
            "-d",
            "--debug",
            help="Show debug information.",
        ),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            ...,
            "-v",
            "--version",
            help="Show the version of Chalk and key dependencies.",
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
    Display detailed information about a Chalk project.
    """
    if (classroom + debug + version) > 1:
        raise ValueError("Only one of --classroom, --debug, or --version can be specified")

    if debug:
        display_debug_info(format=validate_info_format(format))
    elif version:
        display_version_info(format=validate_info_format(format))
    else:
        display_project_info(format=validate_info_format(format))
