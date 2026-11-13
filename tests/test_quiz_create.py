"""
`chalk quiz create` writes a conf.yaml without empty fields, and chalk reads it back.
"""

from typer.testing import CliRunner

from chalk.cli import app
from chalk.core import Classroom


def test_quiz_create_omits_type_of_generic_questions(classroom) -> None:
    result = CliRunner().invoke(app, ["quiz", "create", "pz", "--name", "PZ", "--questions", "2"])
    assert result.exit_code == 0, result.output

    conf = (classroom / "pz" / "conf.yaml").read_text()
    assert "type" not in conf
    assert "null" not in conf

    quiz = next(q for q in Classroom.load().iter_quizzes() if q.id == "pz")
    assert list(quiz.get_questions()) == ["q1", "q2"]

    result = CliRunner().invoke(app, ["show", "pz"])
    assert result.exit_code == 0, result.output
