"""
A quiz question with `source:` that points to a question of a codehood
course uses the grader of graders/<path>/.
"""

import csv
import shutil
from fractions import Fraction
from pathlib import Path

import pytest
from typer.testing import CliRunner

from chalk.cli import app
from chalk.codehood_autograde import (
    GraderLayoutError,
    find_graders,
    find_question_grader,
    make_grader,
)
from chalk.core import Classroom
from tests.test_codehood_autograde import CORRECT, WRONG, add_question, write

needs_swipl = pytest.mark.skipif(not shutil.which("swipl"), reason="swipl is needed")

WHERE = "logico/aritmetica/fatorial-com-is"
SOURCE = f"../questions/{WHERE}.md"


@pytest.fixture
def course(classroom: Path) -> Path:
    """
    The example classroom, which is also a codehood course with a quiz p1
    that reuses the question of the course.
    """
    write(classroom / "codehood.toml", "")
    add_question(classroom)
    conf = classroom / "p1" / "conf.yaml"
    conf.write_text(conf.read_text() + f"  - id: fat\n    source: {SOURCE}\n")
    return classroom


_quizzes: list = []


def question():
    """
    The question `fat`. A question only keeps a weak reference to its quiz,
    so the quiz is kept alive here.
    """
    quiz = Classroom.load().get_quiz("p1")
    _quizzes.append(quiz)
    return quiz.get_question("fat")


class TestFindQuestionGrader:
    def test_finds_the_grader_of_the_question(self, course: Path) -> None:
        found = find_question_grader(course / "questions" / f"{WHERE}.md")
        assert found is not None
        assert found.folder == course / "graders" / WHERE

    def test_none_without_grader_yaml(self, course: Path) -> None:
        (course / "graders" / WHERE / "grader.yaml").unlink()
        assert find_question_grader(course / "questions" / f"{WHERE}.md") is None

    def test_none_without_codehood_toml(self, course: Path) -> None:
        (course / "codehood.toml").unlink()
        assert find_question_grader(course / "questions" / f"{WHERE}.md") is None

    def test_none_outside_questions(self, course: Path) -> None:
        other = write(course / "other" / "q.md", "---\nid: q\n---\n\nx\n")
        assert find_question_grader(other) is None

    def test_invalid_grader_yaml(self, course: Path) -> None:
        write(course / "graders" / WHERE / "grader.yaml", "timeout: [")
        with pytest.raises(GraderLayoutError):
            find_question_grader(course / "questions" / f"{WHERE}.md")

    def test_other_broken_grader_does_not_get_in_the_way(self, course: Path) -> None:
        write(course / "graders" / "outro" / "grader.yaml", "answer: x\n")
        with pytest.raises(GraderLayoutError):
            find_graders(course)
        assert find_question_grader(course / "questions" / f"{WHERE}.md") is not None


class TestQuestion:
    def test_course_grader_is_used(self, course: Path) -> None:
        q = question()
        found = q.find_course_grader()
        assert found is not None
        assert found.folder == course / "graders" / WHERE
        assert q.get_grader() is not None

    def test_script_of_the_quiz_has_priority(self, course: Path) -> None:
        from chalk_grader.script_grader import ScriptGrader

        script = write(course / "p1" / "fat" / "autograde.py", "print(1)\n")
        script.chmod(0o755)
        assert isinstance(question().get_grader(), ScriptGrader)

    def test_reference_answer_is_the_course_solution(self, course: Path) -> None:
        assert question().get_reference_answer() == CORRECT

    def test_make_grader_task(self, course: Path) -> None:
        found = find_question_grader(course / "questions" / f"{WHERE}.md")
        task = make_grader(found, course, quiz_id="p1", question_id="fat").task
        assert (task.quiz_id, task.question_id) == ("p1", "fat")
        assert task.root == course / "graders" / WHERE
        assert task.template == course / "graders" / WHERE / "template"


def submit(course: Path, **answers: str) -> None:
    """
    Write submissions.csv with the answers of the students by id.
    """
    path = course / "p1" / "submissions.csv"
    with path.open("w", newline="") as fd:
        out = csv.writer(fd)
        out.writerow(["id", "fat"])
        out.writerows(answers.items())


def scores(course: Path) -> dict[str, Fraction]:
    """
    The score of each student in grades.csv.
    """
    rows = list(csv.DictReader((course / "p1" / "grades.csv").open()))
    # Rows of feedback and notes, when present, have a `field` column.
    return {
        r["id"]: Fraction(r["fat"]) for r in rows if r["fat"] and r.get("field", "score") == "score"
    }


@needs_swipl
class TestEndToEnd:
    def run(self, *args: str):
        return CliRunner().invoke(app, ["autograde", "p1/fat", *args])

    def test_grades_with_the_course_grader(self, course: Path) -> None:
        submit(course, **{"0001": CORRECT, "0002": WRONG})
        result = self.run()
        assert result.exit_code == 0, result.output
        assert "not graded" not in result.output
        got = scores(course)
        assert got["0001"] == 1
        assert got["0002"] < 1

    def test_fenced_answer(self, course: Path) -> None:
        submit(course, **{"0001": f"Aqui:\n```prolog\n{CORRECT}```\n"})
        result = self.run()
        assert result.exit_code == 0, result.output
        assert scores(course)["0001"] == 1

    def test_check_uses_the_course_solution(self, course: Path) -> None:
        result = self.run("--check")
        assert result.exit_code == 0, result.output
