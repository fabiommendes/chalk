"""
Exchange data with a codehood course that lives in the same repository.

codehood reads grades.csv at the repository root: the first column
identifies the student (school_id, username, github or email) and every
other column is a score that the course's grades.py reads by its header.
chalk writes one column per quiz, with the quiz grade as a percentage, and
leaves every other column and row as it was.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from .util.path import write_text

if TYPE_CHECKING:
    from .core.classroom import Classroom

__all__ = [
    "CODEHOOD_ID_COLUMNS",
    "GradesExport",
    "add_codehoodignore",
    "export_grades",
    "quiz_percentages",
]

#: Headers codehood accepts as the first column of grades.csv.
CODEHOOD_ID_COLUMNS = ("school_id", "username", "github", "email")

#: File at the root of a codehood course that lists the paths `codehood push` skips.
CODEHOODIGNORE = ".codehoodignore"


@dataclass
class GradesExport:
    path: Path
    id_column: str
    columns: list[str]
    students: int
    kept_rows: int = 0
    kept_columns: list[str] = field(default_factory=list)


def quiz_percentages(classroom: Classroom) -> dict[str, dict[str, Decimal]]:
    """
    Map each quiz id to the grade of each student, as a percentage of the
    quiz's maximum. Students without any grade in a quiz are left out.
    """
    result: dict[str, dict[str, Decimal]] = {}
    for quiz in classroom.iter_quizzes():
        questions = quiz.get_questions()
        maximum = sum((q.value for q in questions.values()), Decimal(0))
        if maximum == 0:
            continue

        grades: dict[str, Decimal] = {}
        df = quiz.grades.get_dataframe()
        for student_id, row in df.iterrows():
            values = [v for v in row.tolist() if v is not None and v == v]  # drop None/NaN
            if values:
                total = sum((Decimal(str(v)) for v in values), Decimal(0))
                grades[str(student_id)] = total / maximum * 100
        result[quiz.id] = grades
    return result


def export_grades(classroom: Classroom, path: Path | None = None) -> GradesExport:
    """
    Write the grade of each quiz to codehood's grades.csv.

    Columns named after a quiz are replaced. Other columns, and rows of
    students that are not in the roster, are kept. The id header is the
    roster's id column, which must be one codehood accepts.

    Raises:
        ValueError: the roster's id column is not accepted by codehood, or
            the existing file uses another id column.
    """
    path = path or classroom.root / "grades.csv"
    roster = classroom.get_roster()
    id_column = roster.id_column
    if id_column not in CODEHOOD_ID_COLUMNS:
        options = ", ".join(CODEHOOD_ID_COLUMNS)
        msg = f"codehood cannot match students by {id_column!r}; use one of: {options}"
        raise ValueError(msg)

    header, rows, delimiter = _read_csv(path)
    if header and header[0] != id_column:
        msg = f"{path} identifies students by {header[0]!r}, but the roster uses {id_column!r}"
        raise ValueError(msg)

    grades = quiz_percentages(classroom)
    quiz_ids = list(grades)
    kept_columns = [c for c in header[1:] if c not in grades]
    columns = [id_column, *kept_columns, *quiz_ids]

    by_id = {row[id_column]: row for row in rows if row.get(id_column)}
    others = [row for row in rows if not row.get(id_column)]
    for student_id in roster:
        by_id.setdefault(student_id, {id_column: student_id})

    for student_id, row in by_id.items():
        for quiz_id in quiz_ids:
            value = grades[quiz_id].get(student_id)
            row[quiz_id] = "" if value is None else _format(value)

    stream = io.StringIO()
    writer = csv.DictWriter(
        stream, fieldnames=columns, delimiter=delimiter, lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    writer.writerows([*by_id.values(), *others])
    write_text(path, stream.getvalue(), rotate=False)

    return GradesExport(
        path=path,
        id_column=id_column,
        columns=quiz_ids,
        students=len(roster),
        kept_rows=sum(1 for id in by_id if id not in roster) + len(others),
        kept_columns=kept_columns,
    )


def add_codehoodignore(root: Path, pattern: str, /) -> bool:
    """
    Add a gitignore pattern to the .codehoodignore of the course at root, so
    `codehood push` skips it. Does nothing if root has no codehood.toml.

    A line that already matches pattern, ignoring the spaces around it, is not
    added again. Other lines and comments are kept, and the file ends with a
    newline.

    Returns:
        True if the file was written, False if nothing changed.
    """
    if not (root / "codehood.toml").is_file():
        return False

    path = root / CODEHOODIGNORE
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if pattern in (line.strip() for line in text.splitlines()):
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    write_text(path, f"{text}{pattern}\n", rotate=False)
    return True


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]], str]:
    if not path.exists():
        return [], [], ","
    text = path.read_text(encoding="utf-8")
    first = text.partition("\n")[0]
    delimiter = ";" if ";" in first else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = [{k: v or "" for k, v in row.items() if k is not None} for row in reader]
    return list(reader.fieldnames or []), rows, delimiter


def _format(value: Decimal) -> str:
    text = f"{value.quantize(Decimal('0.01')):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text
