"""
Invalid answers do not abort `chalk autograde`, and error messages do not leak
the repr of an Issue.
"""

from decimal import Decimal
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from chalk.cli import app
from chalk.cli.util import safe
from chalk.core import Classroom
from chalk.core.issue import Issue, error_message, list_of_issues


def write_submissions(classroom: Path, rows: dict[str, str], column: str = "q1") -> None:
    lines = [f"id,{column}"] + [f"{sid},{ans}" for sid, ans in rows.items()]
    (classroom / "p1" / "submissions.csv").write_text("\n".join(lines) + "\n")


def grades_text(classroom: Path) -> str:
    path = classroom / "p1" / "grades.csv"
    return path.read_text() if path.exists() else ""


class TestAutogradeInvalid:
    def test_unknown_choice_does_not_stop_next_student(self, classroom: Path) -> None:
        write_submissions(classroom, {"0001": "xx", "0002": "df"})
        result = CliRunner().invoke(app, ["autograde", "p1/q1"])
        assert result.exit_code == 1
        assert "invalid answer: Answer 'xx' is not one of the choices" in result.output
        assert "Issue(" not in result.output
        grades = grades_text(classroom)
        assert "0002" in grades
        assert "0001" not in grades

    def test_out_of_domain_numeric_is_graded_zero_with_feedback(self, classroom: Path) -> None:
        (classroom / "p1" / "questions" / "n1.yaml").write_text(
            "id: n1\ntype: numeric\nstem: Quanto é 1+2?\nanswer: 3\ndomain: integer\n"
        )
        conf = classroom / "p1" / "conf.yaml"
        conf.write_text(conf.read_text() + "  - id: n1\n")
        write_submissions(classroom, {"0001": "3.5", "0002": "3"}, column="n1")
        result = CliRunner().invoke(app, ["autograde", "p1/n1"])
        assert result.exit_code == 0, result.output
        quiz = Classroom.load().get_quiz("p1")
        question = quiz.get_question("n1")
        assert question.validate_answer("3.5") == 3.5
        graded = question.grade_answer("3.5")
        assert graded.score == Decimal(0)
        assert "not an integer" in graded.feedback
        grades = grades_text(classroom)
        assert "0001" in grades and "0002" in grades


class TestErrorMessage:
    def test_issue(self) -> None:
        assert error_message(ValueError(Issue.error("x", "msg"))) == "msg"
        assert str(Issue.error("code")) == "code"

    def test_list_of_issues(self) -> None:
        exc = ValueError([Issue.error("a", "m1"), Issue.warning("b", "m2")])
        assert error_message(exc) == "m1; m2"

    def test_plain(self) -> None:
        assert error_message(ValueError("plain")) == "plain"

    def test_list_of_issues_unwraps_value_error(self) -> None:
        issue = Issue.error("x", "msg")
        assert list_of_issues(ValueError(issue), ["response"]) == [issue]

    def test_list_of_issues_mapping(self) -> None:
        (issue,) = list_of_issues({"1": "m"}, [], code="e")
        assert issue.code == "e1"


class TestSafe:
    @pytest.mark.parametrize("exc", [typer.Exit(1), typer.Abort()])
    def test_typer_exceptions_pass_through(self, exc: Exception, capsys) -> None:
        @safe
        def run() -> None:
            raise exc

        with pytest.raises(type(exc)):
            run()
        assert "Error" not in capsys.readouterr().err

    def test_issue_message(self, capsys) -> None:
        @safe
        def run() -> None:
            raise ValueError(Issue.error("x", "readable"))

        with pytest.raises(SystemExit):
            run()
        err = capsys.readouterr().err
        assert "Error: readable" in err
        assert "Issue(" not in err
