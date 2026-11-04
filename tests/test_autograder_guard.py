"""
Defenses against a student who forges the report from inside the pytest
process: the audit hook of runners/pytest_guard.py and the notes for the
teacher.
"""

import io
from fractions import Fraction
from pathlib import Path

from chalk.autograder.suspicious import scan
from chalk.core import disqualification as dq
from chalk.core import models
from chalk.core.grades import load_grades_from_path, save_grades_to_path
from tests.test_autograder_pytest import cache, make_grader, project, solution, template
from tests.test_autograder_sandbox import needs_bwrap

__all__ = ["cache", "solution", "template"]

FORGED = """
FORGED = "<testsuites><testsuite>" + "".join(
    f'<testcase classname="{c}" name="{n}"/>'
    for c, n in [
        ("tests.test_calc", "test_add"),
        ("tests.test_calc", "test_sub"),
        ("tests.test_calc.TestMore", "test_add_zero"),
        ("tests.test_calc.TestMore", "test_sub_neg"),
    ]
) + "</testsuite></testsuites>"
"""

ATEXIT = (
    FORGED
    + """
import atexit, os
def forge():
    with open(os.environ["CHALK_RESULT"], "w") as f:
        f.write(FORGED)
atexit.register(forge)
def add(a, b): return 0
def sub(a, b): return 0
"""
)

#: The write runs in a thread with no student code in its stack.
TIMER = (
    FORGED
    + """
import os, threading
from pathlib import Path
threading.Timer(0.5, Path(os.environ["CHALK_RESULT"]).write_text, args=(FORGED,)).start()
def add(a, b): return 0
def sub(a, b): return 0
"""
)

SUBPROCESS = """
import subprocess, sys
def add(a, b):
    return int(subprocess.run([sys.executable, "-c", f"print({a} + {b})"],
                              capture_output=True, text=True).stdout)
def sub(a, b): return a - b
"""


class Cases:
    sandbox = "none"

    def grade(self, template, cache, solution, root, **conf):
        return make_grader(template, cache, solution, sandbox=self.sandbox, **conf)("s1", root)

    def test_atexit_cannot_rewrite_the_report(self, template, cache, solution, tmp_path) -> None:
        graded = self.grade(template, cache, solution, project(tmp_path, ATEXIT))
        assert graded.score == Fraction(1, 4)
        assert "calc.py:" in graded.notes and "registers exit handlers" in graded.notes
        assert "refused open" in graded.notes
        assert "guard" not in (graded.feedback or "")

    def test_thread_cannot_rewrite_the_report(self, template, cache, solution, tmp_path) -> None:
        graded = self.grade(template, cache, solution, project(tmp_path, TIMER))
        assert graded.score == Fraction(1, 4)

    def test_subprocess_is_refused(self, template, cache, solution, tmp_path) -> None:
        root = project(tmp_path, SUBPROCESS)
        graded = self.grade(template, cache, solution, root)
        assert graded.score == Fraction(2, 4)
        assert "refused subprocess.Popen" in graded.notes

    def test_guard_off(self, template, cache, solution, tmp_path) -> None:
        root = project(tmp_path, SUBPROCESS)
        graded = self.grade(template, cache, solution, root, vars={"guard": "off"})
        assert graded.score == 1
        assert graded.notes is None

    def test_module_with_a_standard_name(self, template, cache, solution, tmp_path) -> None:
        root = project(tmp_path, "def add(a, b): return a + b\ndef sub(a, b): return a - b\n")
        # A working copy of the standard module, which pytest loads early.
        (root / "textwrap.py").write_text(
            "import os, sysconfig\n"
            "exec(open(os.path.join(sysconfig.get_paths()['stdlib'], 'textwrap.py')).read())\n"
        )
        graded = self.grade(template, cache, solution, root)
        assert graded.score == dq.Error()
        assert "textwrap (textwrap.py)" in graded.feedback

    def test_clean_solution_has_no_notes(self, template, cache, solution) -> None:
        graded = self.grade(template, cache, solution, solution)
        assert graded.score == 1
        assert graded.notes is None


class TestWithoutSandbox(Cases):
    pass


@needs_bwrap
class TestWithSandbox(Cases):
    sandbox = "bwrap"


class TestScan:
    def test_finds_patterns_with_lines(self, tmp_path: Path) -> None:
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "mod.py").write_text("x = 1\nimport atexit\n")
        (tmp_path / "notes.txt").write_text("see CHALK_RESULT\n")
        patterns = {"**/*.py": {"registers exit handlers": r"\batexit\b"}}
        found = scan(tmp_path, template=None, patterns=patterns)
        assert found == [
            "notes.txt:1: refers to the report file",
            "pkg/mod.py:2: registers exit handlers",
        ]

    def test_skips_template_copies_and_trusted_paths(self, tmp_path: Path) -> None:
        root, template = tmp_path / "root", tmp_path / "template"
        for base in (root, template):
            (base / "tests").mkdir(parents=True)
            (base / "starter.py").write_text("# writes junit\n")
        (root / "tests" / "test_x.py").write_text("# junit\n")
        assert scan(root, template=template, patterns={}, skip=["tests"]) == []
        (root / "starter.py").write_text("# writes junit, changed\n")
        assert scan(root, template=template, patterns={}, skip=["tests"]) == [
            "starter.py:1: refers to JUnit reports"
        ]


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
