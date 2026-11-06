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


# ==============================================================================
# chalk codehood autograde
# ==============================================================================
@app.command(name="autograde")
@safe
def autograde(
    exam: Annotated[
        str | None,
        typer.Option("--exam", metavar="SLUG", help="Exam whose answers are graded."),
    ] = None,
    question: Annotated[
        str | None,
        typer.Option("--question", metavar="SLUG", help="Grade only this question of the exam."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Grade, but write nothing; show the distribution."),
    ] = False,
    server: Annotated[
        str | None,
        typer.Option("--server", metavar="URL", help="Server URL. Default: [server] url."),
    ] = None,
    key_file: Annotated[
        Path | None,
        typer.Option(
            "--key-file", metavar="FILE", help="File with the key of the grading bot (BOT)."
        ),
    ] = None,
    check: Annotated[
        Path | None,
        typer.Option(
            "--check",
            metavar="GRADER",
            help="Grade the reference solution of a grader folder. No server.",
        ),
    ] = None,
    try_: Annotated[
        tuple[Path, Path] | None,
        typer.Option(
            "--try",
            metavar="GRADER FILE",
            help="Grade a local file with a grader folder. No server.",
        ),
    ] = None,
) -> None:
    """
    Grade the code answers of a codehood exam and write the grades back.

    Reads codehood.toml, questions/ and graders/ of the current directory. The
    key of the grading bot comes from CODEHOOD_BOT_KEY or --key-file and is
    never passed to the graded code. Answers with human feedback are skipped.
    """
    from ..codehood_autograde import run_autograde, run_check, run_try

    root = Path.cwd()
    if check is not None:
        run_check(root, check)
    elif try_ is not None:
        run_try(root, *try_)
    else:
        if exam is None:
            raise typer.BadParameter("--exam is required", param_hint="--exam")
        run_autograde(
            root, exam, question=question, dry_run=dry_run, server=server, key_file=key_file
        )
