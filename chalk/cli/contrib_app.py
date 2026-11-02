import importlib
import sys
from pathlib import Path
from typing import Annotated

import rich
import typer
from typer.main import get_command

from .util import safe

__all__ = ["contrib", "add_contrib_command"]


def add_contrib_command(app: typer.Typer) -> None:
    app.command(
        no_args_is_help=False,
        add_help_option=False,
        context_settings={
            "allow_extra_args": True,
            "ignore_unknown_options": True,
        },
    )(contrib)


@safe
def contrib(
    ctx: typer.Context,
    module: Annotated[
        str,
        typer.Argument(
            metavar="MODULE",
            help="Module name",
        ),
    ] = "",
) -> None:
    """
    Load a contrib module.
    """
    if not module:
        list_contrib_modules()
        return

    try:
        module = module.replace("-", "_")
        module = "chalk.contrib." + module
        mod = importlib.import_module(module)
    except ModuleNotFoundError:
        rich.print(f"[b red]Error:[/] module {module!r} not found.", file=sys.stderr)
        raise typer.Exit(1)

    command = get_command(mod.app)
    command.main(ctx.args)


def list_contrib_modules() -> None:
    """
    List all contrib modules.
    """

    rich.print("[b]Available contrib modules:[/]")

    root = Path(__file__).parent.parent / "contrib"
    for base, _, names in root.walk():
        names[:] = [name for name in names if not name.startswith("_")]
        for name in names:
            if name.endswith(".py") and name != "__init__.py":
                mod = Path(base) / name.removesuffix(".py")
                mod = mod.relative_to(root)
                mod = str(mod).replace("/", ".")

                pypath = "chalk.contrib." + mod
                try:
                    app: typer.Typer = importlib.import_module(pypath).app
                except (ModuleNotFoundError, AttributeError):
                    continue

                cmd = get_command(app)
                doc = cmd.callback.__doc__ or "No description available"
                doc, _, _ = doc.partition("\n\n")
                doc = doc.replace("\n", " ").strip()

                rich.print(f" - [bold cyan]{mod.replace('_', '-')}:[/] [not bold]{doc}[/]")
