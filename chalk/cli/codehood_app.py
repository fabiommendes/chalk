from pathlib import Path
from typing import Annotated

import rich
import typer

from ..codehood import export_grades
from ..core import Classroom
from .util import safe

app = typer.Typer(no_args_is_help=True)


# ==============================================================================
# chalk codehood grades
# ==============================================================================
@app.command(name="grades")
@safe
def grades(
    output: Annotated[
        Path | None,
        typer.Option(
            ...,
            "-o",
            "--output",
            help="File to update (default: grades.csv at the project root)",
        ),
    ] = None,
) -> None:
    """
    Write the grade of each quiz, in percent, to codehood's grades.csv.

    Quiz columns are replaced; other columns and rows are kept.
    """
    result = export_grades(Classroom.load(), output)
    quizzes = ", ".join(result.columns) or "none"
    rich.print(f"Updated [b]{result.path}[/] ({result.id_column}): quizzes {quizzes}")
    if result.kept_columns:
        rich.print(f"[dim]Kept columns: {', '.join(result.kept_columns)}[/]")
    if result.kept_rows:
        rich.print(f"[dim]Kept {result.kept_rows} rows of students not in the roster[/]")
