"""
Run every non-interactive command against the example classroom.

These tests only check that commands finish without errors. Tests of
behavior live next to the modules they test.
"""

import pytest
from typer.testing import CliRunner

from chalk.cli import app

COMMANDS = [
    "info",
    "info --debug",
    "info --format json",
    "roster validate --fields name",
    "roster validate --quiz p1",
    "show",
    "show -f json",
    "show -f csv",
    "show -s -name",
    "show --roster",
    "show --roster -s -name -f csv",
    "show p1",
    "show p1 -f yaml",
    "show p1/q1",
    "show p1/q2",
    "show p1/q3",
    "show p1 --grades",
    "show p1/q1 --grades",
    "show --grades",
    "show p1/q3 --answers",
    "show p1/q3 --answers -f json",
    "show p1/q3 --student 0001",
    "autograde p1/q1 --yes",
    "autograde p1/q2 --yes",
    "codehood grades",
    "codehood autograde --help",
    "quiz create p2 --name P2 --questions 3",
    "contrib",
    "contrib --help",
    "clear --autograder",
    "contrib github.classroom --help",
    "contrib github.roster --help",
    "contrib github.repo-submissions --help",
    "contrib grades.rescale --help",
    "contrib parser.elm-test --help",
    "contrib data.convert --help",
]


@pytest.mark.parametrize("command", COMMANDS)
def test_command_runs(classroom, command: str) -> None:
    result = CliRunner().invoke(app, command.split())
    assert result.exit_code == 0, result.output
