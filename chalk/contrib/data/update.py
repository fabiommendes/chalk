import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import IO, Annotated, Any, Literal

import typer
from natsort import natsorted

from chalk.core.answer import serialize_answer
from chalk.data import load_structured_data

app = typer.Typer()

Action = Literal["copy", "move", "link", "relink"]
GithubId = str
StudentId = str


@app.command()
def main(
    source: Annotated[
        Path,
        typer.Argument(
            ...,
            metavar="CONF",
            help="Input configuration file",
        ),
    ] = Path("conf.yaml"),
    force: Annotated[
        bool,
        typer.Option(
            ...,
            "--force",
            "-f",
            help="Overwrite target, if it exists.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            ...,
            "--dry-run",
            "-d",
            help="Perform a trial run with no changes made.",
        ),
    ] = False,
) -> None:
    """
    Update conf.yaml from old format to the new.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source file does not exist: {source}")

    data: Any = load_structured_data(source)
    submissions_target = source.parent / "submissions.csv"
    grades_target = source.parent / "grades.csv"

    if not force and submissions_target.exists():
        raise FileExistsError(f"Target file already exists: {submissions_target}")

    if not force and grades_target.exists():
        raise FileExistsError(f"Target file already exists: {grades_target}")

    process_submissions(
        data["submissions"], sys.stdout if dry_run else submissions_target.open("w")
    )

    process_grades(data["submissions"], sys.stdout if dry_run else grades_target.open("w"))


def process_submissions(submissions: Any, file: IO[str]) -> None:
    """
    Process the submissions data and write to the given file.
    """
    writer = csv.writer(file)

    questions: set[str] = set()
    for sub in submissions.values():
        questions.update(sub.get("responses", {}).keys())

    question_cols = natsorted(questions)
    writer.writerow(["id", "start", "end", *question_cols])
    for id, sub in submissions.items():
        row = [id, isodate(sub.get("start")), isodate(sub.get("end"))]
        responses = sub.get("responses", {})
        for q in question_cols:
            answer = responses.get(q, {}).get("answer")
            row.append(serialize_answer(answer) if answer is not None else None)
        writer.writerow(row)


def process_grades(submissions: Any, file: IO[str]) -> None:
    """
    Process the grades data and write to the given file.
    """
    writer = csv.writer(file)

    questions: set[str] = set()
    for sub in submissions.values():
        questions.update(sub.get("responses", {}).keys())

    question_cols = natsorted(questions)
    writer.writerow(["id", *question_cols])
    for id, sub in submissions.items():
        row = [id]
        responses = sub.get("responses", {})
        for q in question_cols:
            grade = responses.get(q, {}).get("grade")
            row.append(str(grade))
        writer.writerow(row)


def isodate(value: datetime | str | None) -> str | None:
    """
    Convert a datetime or string to ISO 8601 format.
    """
    if value is None or isinstance(value, str):
        return value
    return value.isoformat()


if __name__ == "__main__":
    app()
