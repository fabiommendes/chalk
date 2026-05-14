import sys

import rich
import typer

from ..roster import read_roster
from ..util import render_table
from .util import safe

app = typer.Typer()


@app.command()
@safe
def students():
    """
    List students in the roster.
    """
    roster = read_roster()
    if not roster:
        rich.print("[b yellow]Warning:[/] roster is empty!", file=sys.stderr)
        return

    data = roster.model_dump()
    render_table(data, styles={"id": "cyan"}, align={"id": "right"})
