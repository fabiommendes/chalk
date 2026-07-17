import sys
from pathlib import Path
from typing import Annotated

import rich
import typer

from chalk.util.show import render_file_tree

app = typer.Typer()


@app.command()
def main(
    path: Annotated[
        Path | None,
        typer.Argument(
            ...,
            metavar="PATH",
        ),
    ] = None,
    depth: Annotated[
        int | None,
        typer.Option(
            ...,
            "--depth",
            "-d",
            help="Limit the depth of the tree.",
        ),
    ] = None,
):
    """
    Show the file tree under given PATH.
    """
    if path is None:
        path = Path.cwd()
    rich.print(render_file_tree(path, depth=sys.maxsize if depth is None else depth))


if __name__ == "__main__":
    app()
