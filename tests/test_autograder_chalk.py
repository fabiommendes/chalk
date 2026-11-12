"""
The autograder as chalk uses it: profiles in chalk.toml, the grader of a
question, `chalk autograde --check` and notes in grades.csv.
"""

import io
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

from chalk.cli.autograde_cmd import check_autograder
from chalk.core import Classroom, models
from chalk.core import disqualification as dq
from chalk.core.grader import Graded
from chalk.core.grades import load_grades_from_path, save_grades_to_path
from chalk_grader.profile_grader import ProfileGrader


class TestCheck:
    def question(self, graded, reference="solution"):
        return SimpleNamespace(
            get_grader=lambda: lambda id, answer, **kw: graded,
            get_reference_answer=lambda: reference,
        )

    def test_full_score_passes(self) -> None:
        check_autograder(self.question(Graded(Fraction(1))), timeout=None, keep_files=False)  # type: ignore[arg-type]

    @pytest.mark.parametrize("score", [Fraction(3, 4), dq.Error()])
    def test_partial_score_fails(self, score) -> None:
        with pytest.raises(typer.Exit):
            check_autograder(self.question(Graded(score)), timeout=None, keep_files=False)  # type: ignore[arg-type]

    def test_needs_reference(self) -> None:
        with pytest.raises(typer.BadParameter):
            check_autograder(self.question(Graded(1), None), timeout=None, keep_files=False)  # type: ignore[arg-type]


def test_notes_round_trip_in_the_grades_file(tmp_path: Path) -> None:
    grades = {
        "s1": models.SubmissionGrade(
            id="s1",
            responses={
                "q1": models.ResponseGrade(score=Fraction(1), notes="calc.py:3: uses atexit"),
                "q2": models.ResponseGrade(score=Fraction(1, 2), feedback="almost"),
            },
        ),
        "s2": models.SubmissionGrade(id="s2", responses={"q1": models.ResponseGrade(score=0)}),
    }
    out = io.StringIO()
    save_grades_to_path(grades, out, ["q1", "q2"])
    lines = out.getvalue().splitlines()
    assert lines[0] == "id,field,q1,q2"
    assert lines[1:4] == [
        "s1,score,1.00,0.50",
        ",feedback,,almost",
        ",notes,calc.py:3: uses atexit,",
    ]

    path = tmp_path / "grades.csv"
    path.write_text(out.getvalue())
    quiz = type("Quiz", (), {"id": "p1"})()
    loaded = load_grades_from_path(path, quiz)
    assert loaded._grades["s1"].responses["q1"].notes == "calc.py:3: uses atexit"
    assert loaded._grades["s1"].responses["q2"].notes is None


def test_classroom_reads_profiles(classroom: Path) -> None:
    with (classroom / "chalk.toml").open("a") as fd:
        fd.write('\n[profiles.mine]\nextends = "python-pytest"\n')
    assert Classroom.load(classroom).profiles == {"mine": {"extends": "python-pytest"}}


def test_question_uses_profile_from_chalk_toml(classroom: Path) -> None:
    with (classroom / "chalk.toml").open("a") as fd:
        fd.write('\n[profiles.mine]\nextends = "python-pytest"\nenv.X = "1"\n')
    conf = classroom / "p1" / "conf.yaml"
    entry = "  - id: q3\n    autograder:\n      profile: mine\n"
    conf.write_text(conf.read_text().replace("  - id: q3\n", entry))
    # Keep the classroom alive: questions hold only weak references to it.
    room = Classroom.load()
    grader = room.get_quiz("p1").get_question("q3").get_grader()
    assert isinstance(grader, ProfileGrader)
    assert grader.name == "mine"
    assert grader.spec.env["X"] == "1"


def test_question_with_unknown_profile(classroom: Path) -> None:
    conf = classroom / "p1" / "conf.yaml"
    entry = "  - id: q3\n    autograder:\n      profile: nope\n"
    conf.write_text(conf.read_text().replace("  - id: q3\n", entry))
    with pytest.raises(ValueError, match="unknown profile"):
        # Keep the classroom alive: questions hold only weak references to it.
        room = Classroom.load()
        room.get_quiz("p1").get_question("q3").get_grader()


def test_parse_build_error() -> None:
    assert dq.parse(str(dq.BuildError())) == dq.BuildError()
