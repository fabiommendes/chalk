"""
Behavior of `chalk show` that the smoke tests do not check, and of the table
sorting it relies on.
"""

import json
from decimal import Decimal

import pytest
from typer.testing import CliRunner

import chalk.core  # noqa: F401  (chalk.table imports chalk.data)
from chalk.cli import app
from chalk.cli.util import parse_sort
from chalk.table import Table


def run(*args: str):
    return CliRunner().invoke(app, list(args))


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, (None, False)), ("name", ("name", False)), ("-name", ("name", True)),
     ("+name", ("name", False))],
)  # fmt: skip
def test_parse_sort(value, expected) -> None:
    assert parse_sort(value) == expected


def test_table_sorts_numbers_by_value() -> None:
    table = Table(
        [{"q1": Decimal("10")}, {"q1": Decimal("-0.5")}, {"q1": None}, {"q1": Decimal("9")}],
        index=["a", "b", "c", "d"],
    )
    rendered = table.render(sort="q1")
    ids = list(rendered.columns[0].cells)  # type: ignore[union-attr]
    assert ids == ["c", "b", "d", "a"]


def test_show_json_without_loc_is_the_classroom_info(classroom) -> None:
    result = run("show", "-f", "json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["classroom"] == "turma"
    assert [q["id"] for q in data["quizzes"]] == ["p1"]


def test_show_roster_csv_sorted_descending(classroom) -> None:
    result = run("show", "--roster", "-s", "-name", "-f", "csv")
    assert result.exit_code == 0, result.output
    ids = [line.split(",")[0] for line in result.output.splitlines()[1:]]
    assert ids == ["0003", "0002", "0001"]


def test_show_answers_json(classroom) -> None:
    result = run("show", "p1/q3", "--answers", "-f", "json")
    assert result.exit_code == 0, result.output
    assert set(json.loads(result.output)) == {"0001", "0003"}


@pytest.mark.parametrize(
    "args",
    [
        ["show", "p1", "--answers"],
        ["show", "--roster", "p1"],
        ["show", "p1", "--student", "0001"],
        ["show", "p9"],
    ],
)
def test_show_rejects(classroom, args) -> None:
    assert run(*args).exit_code != 0
