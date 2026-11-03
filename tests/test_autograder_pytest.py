import shutil
import subprocess
import textwrap
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

from chalk.autograder.profile_grader import ProfileGrader, resolve_profile
from chalk.autograder.profiles import PrepareError, install_trusted_files, score_report
from chalk.cli.autograde_cmd import check_autograder
from chalk.core import disqualification as dq
from chalk.core import models
from chalk.core.grader import Graded
from tests.test_autograder_sandbox import needs_bwrap

TESTS = """
from calc import add, sub

def test_add():
    assert add(1, 2) == 3

def test_sub():
    assert sub(3, 2) == 1

class TestMore:
    def test_add_zero(self):
        assert add(0, 0) == 0

    def test_sub_neg(self):
        assert sub(0, 1) == -1
"""

PYPROJECT = """
[project]
name = "calc"
version = "0"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = ["pytest"]
"""

SOLUTION = "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"


def junit(*cases: str) -> str:
    return f"<testsuites><testsuite>{''.join(cases)}</testsuite></testsuites>"


class TestScore:
    keys = (("tests.test_a", "test_x"), ("tests.test_a.TestK", "test_y[a::b]"))
    expected = {k: "::".join(k) for k in keys}

    def test_all_pass(self) -> None:
        src = junit(
            '<testcase classname="tests.test_a" name="test_x"/>',
            '<testcase classname="tests.test_a.TestK" name="test_y[a::b]"/>',
        )
        assert score_report(src, self.expected).score == 1

    def test_missing_counts_as_failure(self) -> None:
        graded = score_report(
            junit('<testcase classname="tests.test_a" name="test_x"/>'), self.expected
        )
        assert graded.score == Fraction(1, 2)
        assert "test_y[a::b] (not run)" in (graded.feedback or "")

    def test_skipped_and_failed_count_as_failure(self) -> None:
        src = junit(
            '<testcase classname="tests.test_a" name="test_x"><skipped/></testcase>',
            '<testcase classname="tests.test_a.TestK" name="test_y[a::b]"><failure/></testcase>',
        )
        assert score_report(src, self.expected).score == 0

    def test_unknown_tests_are_ignored(self) -> None:
        src = junit(
            '<testcase classname="tests.test_a" name="test_x"/>',
            '<testcase classname="tests.test_fake" name="test_1"/>',
            '<testcase classname="tests.test_fake" name="test_2"/>',
        )
        assert score_report(src, self.expected).score == Fraction(1, 2)

    def test_repeated_entry_with_failure(self) -> None:
        src = junit(
            '<testcase classname="tests.test_a" name="test_x"><failure/></testcase>',
            '<testcase classname="tests.test_a" name="test_x"/>',
        )
        assert score_report(src, self.expected).score == 0

    def test_collection_error_in_feedback(self) -> None:
        src = junit(
            '<testcase classname="" name="tests.test_a"><error message="collection failure"/></testcase>'
        )
        graded = score_report(src, self.expected)
        assert graded.score == 0
        assert "tests.test_a: collection failure" in (graded.feedback or "")

    def test_invalid_report(self) -> None:
        assert score_report("<oops", self.expected).score == dq.Error()


class TestTrustedFiles:
    def test_replaces_tests_and_removes_conftest(self, tmp_path: Path) -> None:
        template = tmp_path / "template"
        (template / "tests").mkdir(parents=True)
        (template / "tests" / "test_a.py").write_text("ok")
        root = tmp_path / "root"
        (root / "tests").mkdir(parents=True)
        (root / "tests" / "test_a.py").write_text("changed")
        (root / "tests" / "test_fake.py").write_text("fake")
        (root / "conftest.py").write_text("evil")

        overlays = install_trusted_files(root, template, ["tests", "conftest.py"])
        assert sorted(p.name for p in (root / "tests").iterdir()) == ["test_a.py"]
        assert (root / "tests" / "test_a.py").read_text() == "ok"
        assert not (root / "conftest.py").exists()
        assert overlays == [(template / "tests", root / "tests")]

    @pytest.mark.parametrize("name", ["../x", "/etc", "-p"])
    def test_rejects_paths_outside_the_template(self, tmp_path: Path, name: str) -> None:
        with pytest.raises(ValueError):
            install_trusted_files(tmp_path, tmp_path, [name])


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("q") / "template"
    (path / "tests").mkdir(parents=True)
    (path / "pyproject.toml").write_text(PYPROJECT)
    (path / "tests" / "test_calc.py").write_text(TESTS)
    lock = subprocess.run(["uv", "lock", "--offline"], cwd=path, capture_output=True, text=True)
    if lock.returncode != 0:
        pytest.skip(f"cannot lock the template offline: {lock.stderr}")
    return path


@pytest.fixture(scope="module")
def cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("cache")


def make_grader(template: Path, cache: Path, solution: Path | None, **conf) -> ProfileGrader:
    question = SimpleNamespace(
        id="q1",
        quiz=SimpleNamespace(id="p1"),
        root=template.parent,
        get_template_path=lambda: template,
    )
    conf = {"profile": "python-pytest", "timeout": 60, **conf}
    return ProfileGrader(
        script=None,
        question=question,  # type: ignore[arg-type]
        conf=models.Autograder(**conf),
        name="python-pytest",
        profile=resolve_profile("python-pytest"),
        solution=solution,
        cache_dir=cache,
    )


def project(tmp_path: Path, calc: str, files: dict[str, str] | None = None) -> Path:
    root = tmp_path / "student"
    root.mkdir()
    (root / "calc.py").write_text(textwrap.dedent(calc))
    for name, content in (files or {}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content))
    return root


@pytest.fixture
def solution(tmp_path: Path) -> Path:
    path = tmp_path / "solution"
    path.mkdir()
    (path / "calc.py").write_text(SOLUTION)
    return path


class Cases:
    """
    Student projects graded with and without the sandbox.
    """

    sandbox = "none"

    def grade(self, template, cache, solution, root):
        return make_grader(template, cache, solution, sandbox=self.sandbox)("s1", root)

    def test_solution_gets_full_score(self, template, cache, solution) -> None:
        assert self.grade(template, cache, solution, solution).score == 1

    def test_partial_score(self, template, cache, solution, tmp_path) -> None:
        root = project(tmp_path, "def add(a, b): return a + b\ndef sub(a, b): return 0\n")
        graded = self.grade(template, cache, solution, root)
        assert graded.score == Fraction(2, 4)
        assert "tests.test_calc::test_sub" in (graded.feedback or "")

    def test_import_error_scores_zero(self, template, cache, solution, tmp_path) -> None:
        root = project(tmp_path, "")
        (root / "calc.py").unlink()
        graded = self.grade(template, cache, solution, root)
        assert graded.score == 0
        assert "(not run)" in (graded.feedback or "")

    def test_deleted_and_fake_tests_do_not_count(self, template, cache, solution, tmp_path) -> None:
        root = project(
            tmp_path,
            "def add(a, b): return a + b\ndef sub(a, b): return 0\n",
            {
                "tests/test_calc.py": "",
                "tests/test_fake.py": "def test_1(): pass\ndef test_2(): pass\n",
            },
        )
        assert self.grade(template, cache, solution, root).score == Fraction(2, 4)

    def test_student_conftest_is_ignored(self, template, cache, solution, tmp_path) -> None:
        conftest = """
            import pytest
            @pytest.hookimpl(tryfirst=True)
            def pytest_runtest_call(item):
                raise SystemExit
            def pytest_collection_modifyitems(items):
                items.clear()
        """
        root = project(
            tmp_path,
            "def add(a, b): return 0\ndef sub(a, b): return 0\n",
            {"conftest.py": conftest},
        )
        assert self.grade(template, cache, solution, root).score == Fraction(1, 4)

    def test_printed_result_does_not_count(self, template, cache, solution, tmp_path) -> None:
        root = project(
            tmp_path,
            "print('CHALK_RESULT: 1.0')\ndef add(a, b): return 0\ndef sub(a, b): return 0\n",
        )
        assert self.grade(template, cache, solution, root).score == Fraction(1, 4)


class TestWithoutSandbox(Cases):
    def test_venv_is_cached(self, template, cache, solution) -> None:
        self.grade(template, cache, solution, solution)
        assert len([p for p in cache.glob("python-pytest-*") if p.is_dir()]) == 1

    def test_collection_fails_without_solution(self, template, cache) -> None:
        grader = make_grader(template, cache, None, sandbox="none")
        with pytest.raises(PrepareError, match="reference solution"):
            grader.prepare()

    def test_template_without_lock(self, tmp_path, cache) -> None:
        template = tmp_path / "template"
        template.mkdir()
        (template / "pyproject.toml").write_text(PYPROJECT)
        with pytest.raises(PrepareError, match=r"uv\.lock"):
            make_grader(template, cache, None, sandbox="none").prepare()


@needs_bwrap
class TestWithSandbox(Cases):
    sandbox = "bwrap"

    def test_tests_are_read_only(self, template, cache, solution, tmp_path) -> None:
        calc = """
            from pathlib import Path
            try:
                Path("tests/test_calc.py").write_text("def test_ok(): pass\\n")
            except OSError:
                pass
            def add(a, b): return 0
            def sub(a, b): return 0
        """
        root = project(tmp_path, calc)
        assert self.grade(template, cache, solution, root).score == Fraction(1, 4)
        assert "assert add(1, 2) == 3" in (template / "tests" / "test_calc.py").read_text()

    def test_home_is_hidden(self, template, cache, solution, tmp_path) -> None:
        calc = f"""
            from pathlib import Path
            VISIBLE = Path({str(template / "pyproject.toml")!r}).exists()
            def add(a, b): return a + b if not VISIBLE else 0
            def sub(a, b): return a - b
        """
        root = project(tmp_path, calc)
        if not str(template).startswith(("/home", "/tmp")):
            pytest.skip("template is not under a hidden directory")
        assert self.grade(template, cache, solution, root).score == 1


def test_copy_of_solution_is_not_changed(template, cache, solution) -> None:
    before = shutil.copytree(solution, solution.parent / "before")
    make_grader(template, cache, solution, sandbox="none")("s1", solution)
    assert sorted(p.name for p in solution.iterdir()) == sorted(p.name for p in before.iterdir())


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
