from pathlib import Path

import pytest
from typer.testing import CliRunner

from chalk.cli import app
from chalk.codehood import export_grades
from chalk.core import Classroom


def run(*args: str) -> str:
    result = CliRunner().invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


@pytest.fixture
def graded(classroom: Path) -> Path:
    run("autograde", "p1/q1", "--yes")
    run("autograde", "p1/q2", "--yes")
    return classroom


def read(path: Path) -> list[str]:
    return path.read_text().splitlines()


def test_creates_grades_csv_with_quiz_percentages(graded: Path) -> None:
    run("codehood", "grades")
    # p1: q1 (value 1) + q2 (value 2) graded; q3 has no grades. Max is 4.
    # 0001: 1 + 2 = 3 -> 75%. 0003: 0.66 of q2 -> 16.5%.
    assert read(graded / "grades.csv") == [
        "school_id,p1",
        "0001,75",
        "0002,-29",
        "0003,16.5",
    ]
    assert not list(graded.glob(".grades.bak*"))


def test_keeps_other_columns_and_rows(graded: Path) -> None:
    (graded / "grades.csv").write_text("school_id,trabalho,p1\n0001,80,0\n9999,50,10\n")
    result = export_grades(Classroom.load())
    assert result.kept_columns == ["trabalho"]
    assert read(graded / "grades.csv") == [
        "school_id,trabalho,p1",
        "0001,80,75",
        "9999,50,",
        "0002,,-29",
        "0003,,16.5",
    ]


def test_keeps_semicolon_delimiter(graded: Path) -> None:
    (graded / "grades.csv").write_text("school_id;trabalho\n0001;80\n")
    export_grades(Classroom.load())
    assert read(graded / "grades.csv")[0] == "school_id;trabalho;p1"


def test_rejects_other_id_column_in_file(graded: Path) -> None:
    (graded / "grades.csv").write_text("username,trabalho\nalice,80\n")
    with pytest.raises(ValueError, match="username"):
        export_grades(Classroom.load())


def test_rejects_id_column_codehood_does_not_know(classroom: Path) -> None:
    roster = classroom / "roster.csv"
    roster.write_text(roster.read_text().replace("school_id", "matricula", 1))
    toml = classroom / "chalk.toml"
    toml.write_text(toml.read_text() + 'student_id = "matricula"\n')
    with pytest.raises(ValueError, match="matricula"):
        export_grades(Classroom.load())
