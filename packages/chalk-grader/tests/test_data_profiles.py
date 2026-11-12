"""
Profiles written as data: resolution of `extends` and a profile of shell
scripts, which runs every step without a language toolchain.
"""

import os
from fractions import Fraction
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_sandbox import needs_bwrap

from chalk_grader import disqualification as dq
from chalk_grader import models
from chalk_grader.profile_grader import (
    ProfileGrader,
    builtin_profiles,
    render,
    resolve_profile,
    seed_workdir,
)
from chalk_grader.profiles import PrepareError
from chalk_grader.task import Task

RUNNER = """\
echo '<testsuites><testsuite>'
for t in tests/*.sh; do
  n=$(basename "$t" .sh)
  if sh "$t" >/dev/null 2>&1; then
    echo "<testcase classname=\\"sh\\" name=\\"$n\\"/>"
  else
    echo "<testcase classname=\\"sh\\" name=\\"$n\\"><failure/></testcase>"
  fi
done
echo '</testsuite></testsuites>'
"""

SHELL = {
    "shell-tests": {
        "key": ["tests/inc.sh"],
        "probe": {"greeting": "echo hello"},
        "env": {"GREETING": "{greeting}"},
        "files": {"run.sh": RUNNER},
        "prepare": {"commands": ["echo prepared > {cache}/stamp"]},
        "build": {"command": "sh -n prog.sh", "seed": {"stamp": "{cache}/stamp"}},
        "test": {"command": 'sh {cache}/run.sh > "$CHALK_RESULT"'},
    }
}

TESTS = {
    "inc.sh": '[ "$(sh prog.sh 1)" = 2 ]',
    "inc_zero.sh": '[ "$(sh prog.sh 0)" = 1 ]',
    "seeded.sh": "grep -q prepared stamp",
    "env.sh": '[ "$GREETING" = hello ]',
}


@pytest.fixture
def template(tmp_path: Path) -> Path:
    path = tmp_path / "q" / "template"
    (path / "tests").mkdir(parents=True)
    for name, body in TESTS.items():
        (path / "tests" / name).write_text(body)
    return path


def project(root: Path, prog: str) -> Path:
    root.mkdir(parents=True)
    (root / "prog.sh").write_text(prog)
    return root


@pytest.fixture
def solution(tmp_path: Path) -> Path:
    return project(tmp_path / "solution", "echo $(($1 + 1))\n")


def make_grader(template: Path, solution: Path | None, profiles=SHELL, **conf) -> ProfileGrader:
    task = Task("q1", "p1", root=template.parent, template=template)
    return ProfileGrader(
        script=None,
        task=task,
        conf=models.Autograder(profile="shell-tests", timeout=30, **conf),
        name="shell-tests",
        profile=resolve_profile("shell-tests", profiles),
        solution=solution,
        cache_dir=template.parent / "cache",
    )


class TestResolve:
    def test_builtin_profiles_are_valid(self) -> None:
        for name in builtin_profiles():
            resolve_profile(name)

    def test_extends_merges_tables(self) -> None:
        user = {"pytest-fast": {"extends": "python-pytest", "env": {"X": "1"}}}
        profile = resolve_profile("pytest-fast", user)
        assert profile.env["X"] == "1"
        assert profile.env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
        assert profile.key == ["pyproject.toml", "uv.lock"]

    def test_extends_builtin_with_the_same_name(self) -> None:
        user = {"python-pytest": {"extends": "python-pytest", "tests": ["spec"]}}
        profile = resolve_profile("python-pytest", user)
        assert profile.tests == ["spec"]
        assert profile.prepare.commands

    def test_user_profile_replaces_builtin(self) -> None:
        user = {"rust-cargo": {"test": {"command": "true"}}}
        assert resolve_profile("rust-cargo", user).build is None

    def test_unknown_profile(self) -> None:
        with pytest.raises(ValueError, match="known profiles: .*python-pytest"):
            resolve_profile("nope")

    def test_loop(self) -> None:
        user = {"a": {"extends": "b"}, "b": {"extends": "a"}}
        with pytest.raises(ValueError, match="loop"):
            resolve_profile("a", user)

    def test_unknown_key(self) -> None:
        with pytest.raises(ValidationError):
            resolve_profile("x", {"x": {"test": {"command": "true"}, "tset": {}}})

    def test_render(self) -> None:
        assert render("{a}/b ${HOME} {c}", {"a": "1"}) == "1/b ${HOME} {c}"


def test_seed_touches_student_files(tmp_path: Path) -> None:
    source = tmp_path / "cache" / "target"
    source.mkdir(parents=True)
    (source / "old").write_text("")
    os.utime(source / "old", (0, 0))
    root = project(tmp_path / "s", "")
    os.utime(root / "prog.sh", (0, 0))

    seed_workdir(root, {"target": source})
    assert (root / "target" / "old").stat().st_mtime == 0
    assert (root / "prog.sh").stat().st_mtime > 0


class Cases:
    sandbox = "none"

    def grade(self, template, solution, root, **conf):
        return make_grader(template, solution, sandbox=self.sandbox, **conf)("s1", root)

    def test_solution_gets_full_score(self, template, solution) -> None:
        assert self.grade(template, solution, solution).score == 1

    def test_partial_score(self, template, solution, tmp_path) -> None:
        graded = self.grade(template, solution, project(tmp_path / "s", "echo 2\n"))
        assert graded.score == Fraction(3, 4)
        assert "sh::inc_zero" in (graded.feedback or "")

    def test_build_error(self, template, solution, tmp_path) -> None:
        graded = self.grade(template, solution, project(tmp_path / "s", "if then\n"))
        assert graded.score == dq.BuildError()
        assert "does not compile" in (graded.feedback or "")

    def test_student_tests_do_not_count(self, template, solution, tmp_path) -> None:
        root = project(tmp_path / "s", "echo 0\n")
        (root / "tests").mkdir()
        (root / "tests" / "inc.sh").write_text("true")
        (root / "tests" / "fake.sh").write_text("true")
        assert self.grade(template, solution, root).score == Fraction(2, 4)


class TestWithoutSandbox(Cases):
    def test_cache_is_reused(self, template, solution) -> None:
        make_grader(template, solution, sandbox="none").prepare()
        make_grader(template, solution, sandbox="none").prepare()
        dirs = [p for p in (template.parent / "cache").iterdir() if p.is_dir()]
        assert len(dirs) == 1

    def test_missing_key_file(self, template) -> None:
        (template / "tests" / "inc.sh").unlink()
        with pytest.raises(PrepareError, match=r"tests/inc\.sh"):
            make_grader(template, None, sandbox="none").prepare()

    def test_failed_probe(self, template, solution) -> None:
        profiles = {"shell-tests": {**SHELL["shell-tests"], "probe": {"x": "exit 3"}}}
        with pytest.raises(PrepareError, match="probe 'x'"):
            make_grader(template, solution, profiles, sandbox="none").prepare()

    def test_reference_without_tests(self, template, solution) -> None:
        profiles = {"shell-tests": {**SHELL["shell-tests"], "test": {"command": "true"}}}
        with pytest.raises(PrepareError, match="no tests"):
            make_grader(template, solution, profiles, sandbox="none").prepare()


@needs_bwrap
class TestWithSandbox(Cases):
    sandbox = "bwrap"
