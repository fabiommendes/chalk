"""
The c-make, stdio, c-stdio and elm-test profiles, written only as data.
"""

import json
import shutil
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from test_cgroup import needs_cgroup
from test_sandbox import needs_bwrap

from chalk_grader import cgroup, models
from chalk_grader import disqualification as dq
from chalk_grader.profile_grader import ProfileGrader, resolve_profile, step_memory, with_limits
from chalk_grader.profiles import PrepareError, read_stdio_report
from chalk_grader.runners.stdio import compare
from chalk_grader.task import Task

SANDBOXES = ["none", pytest.param("bwrap", marks=needs_bwrap)]


def make_tree(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content)
    root.mkdir(parents=True, exist_ok=True)
    return root


def grader(
    profile: str, template: Path, solution: Path | None, cache: Path | None = None, **conf
) -> ProfileGrader:
    task = Task("q1", "p1", root=template.parent, template=template)
    return ProfileGrader(
        script=None,
        task=task,
        conf=models.Autograder(profile=profile, timeout=120, **conf),
        name=profile,
        profile=resolve_profile(profile),
        solution=solution,
        cache_dir=cache or template.parent.parent / "cache",
    )


class TestCompare:
    @pytest.mark.parametrize(
        ("mode", "output", "result"),
        [
            ("lines", "1  \n2\n\n", None),
            ("lines", "1\n3\n", "line 2: expected '2', got '3'"),
            ("lines", "1\n", "output ends before line 2, expected '2'"),
            ("lines", "1\n2\n3\n", "unexpected line 3: '3'"),
            ("tokens", " 1   2 ", None),
            ("exact", "1\n2", "line 2: expected '2\\n', got '2'"),
        ],
    )
    def test_modes(self, mode, output, result) -> None:
        assert compare(output, "1\n2\n", mode) == result

    def test_report(self, tmp_path: Path) -> None:
        make_tree(tmp_path, {"tests/a.out": "1\n", "tests/b.out": "2\n", "tests/c.out": "3\n"})
        report = tmp_path / "report.json"
        cases = [
            {"name": "tests/a", "error": None, "output": "1\n"},
            {"name": "tests/b", "error": "timed out after 5s", "output": ""},
        ]
        report.write_text(json.dumps({"cases": cases}))
        expected = {("stdio", n): n for n in ("tests/a", "tests/b", "tests/c")}
        graded = read_stdio_report(report, expected, tmp_path, "lines")
        assert graded.score == Fraction(1, 3)
        assert graded.feedback == (
            "Failed tests:\n- tests/b: timed out after 5s\n- tests/c (not run)"
        )


#
# stdio
#
STDIO_TESTS = {
    "tests/01.in": "1 2\n",
    "tests/01.out": "3\n",
    "tests/02.in": "10 -3\n",
    "tests/02.out": "7\n",
    "tests/03.in": "0 0\n",
    "tests/03.out": "0\n",
}


@pytest.fixture
def stdio_template(tmp_path: Path) -> Path:
    return make_tree(tmp_path / "q" / "template", STDIO_TESTS)


@pytest.mark.parametrize("sandbox", SANDBOXES)
class TestStdio:
    run = {"run": "python3 main.py"}

    def grade(self, template, solution, root, sandbox):
        return grader("stdio", template, solution, sandbox=sandbox, vars=self.run)("s1", root)

    def test_scores(self, stdio_template, tmp_path, sandbox) -> None:
        solution = make_tree(tmp_path / "sol", {"main.py": "print(sum(map(int, input().split())))"})
        assert self.grade(stdio_template, solution, solution, sandbox).score == 1

        wrong = make_tree(
            tmp_path / "s", {"main.py": "a, b = map(int, input().split())\nprint(a + abs(b))"}
        )
        graded = self.grade(stdio_template, solution, wrong, sandbox)
        assert graded.score == Fraction(2, 3)
        assert graded.feedback == "Failed tests:\n- tests/02: line 1: expected '7', got '13'"

    def test_expected_outputs_are_hidden(self, stdio_template, tmp_path, sandbox) -> None:
        solution = make_tree(tmp_path / "sol", {"main.py": "print(sum(map(int, input().split())))"})
        cheat = """
import sys
from pathlib import Path
data = sys.stdin.read()
for case in Path("tests").glob("*.in"):
    out = case.with_suffix(".out")
    if case.read_text() == data and out.exists():
        print(out.read_text(), end="")
"""
        root = make_tree(tmp_path / "s", {"main.py": cheat})
        assert self.grade(stdio_template, solution, root, sandbox).score == 0

    def test_timeout_and_crash(self, stdio_template, tmp_path, sandbox) -> None:
        solution = make_tree(tmp_path / "sol", {"main.py": "print(sum(map(int, input().split())))"})
        program = (
            "import sys\na, b = map(int, input().split())\n"
            "if a == 10:\n    while True: pass\n"
            "if a == 0:\n    sys.exit(3)\nprint(a + b)\n"
        )
        root = make_tree(tmp_path / "s", {"main.py": program})
        graded = grader(
            "stdio",
            stdio_template,
            solution,
            sandbox=sandbox,
            vars={**self.run, "test_timeout": "1"},
        )("s1", root)
        assert graded.score == Fraction(1, 3)
        assert "tests/02: timed out after 1s" in (graded.feedback or "")
        assert "tests/03: exited with code 3" in (graded.feedback or "")

    @needs_cgroup
    def test_memory_limit(self, stdio_template, tmp_path, sandbox) -> None:
        solution = make_tree(tmp_path / "sol", {"main.py": "print(sum(map(int, input().split())))"})
        program = (
            "a, b = map(int, input().split())\n"
            "if a == 10:\n    x = bytearray(b'y') * (400 * 2**20)\n"
            "print(a + b)\n"
        )
        root = make_tree(tmp_path / "s", {"main.py": program})

        def grade(memory: str):
            limits = models.Limits(memory=memory)
            g = grader(
                "stdio", stdio_template, solution, sandbox=sandbox, vars=self.run, limits=limits
            )
            return g("s1", root)

        graded = grade("200MiB")
        assert graded.score == dq.MemoryLimit()
        assert graded.feedback == "The answer used more than 200 MiB of memory."
        assert grade("1GiB").score == 1

    def test_default_memory_is_not_the_address_space(
        self, stdio_template, tmp_path, sandbox, no_cgroups
    ) -> None:
        # 1 GiB of address space, twice the default memory, barely touched.
        program = "x = bytearray(2**30)\nprint(sum(map(int, input().split())))"
        solution = make_tree(tmp_path / "sol", {"main.py": program})
        assert self.grade(stdio_template, solution, solution, sandbox).score == 1

    def test_reference_that_fails_every_case(self, stdio_template, tmp_path, sandbox) -> None:
        solution = make_tree(tmp_path / "sol", {"main.py": "raise SystemExit(2)"})
        with pytest.raises(PrepareError, match="every case"):
            grader("stdio", stdio_template, solution, sandbox=sandbox, vars=self.run).prepare()


@pytest.mark.skipif(not shutil.which("cc"), reason="cc is needed")
@pytest.mark.parametrize("sandbox", SANDBOXES)
def test_c_stdio(stdio_template, tmp_path, sandbox) -> None:
    main = '#include <stdio.h>\nint main(void) { int a, b; scanf("%d %d", &a, &b); '
    solution = make_tree(tmp_path / "sol", {"main.c": main + 'printf("%d\\n", a + b); }\n'})
    g = grader("c-stdio", stdio_template, solution, sandbox=sandbox)
    assert g("s1", solution).score == 1
    wrong = make_tree(tmp_path / "s", {"main.c": main + 'printf("%d\\n", a * b); }\n'})
    assert g("s2", wrong).score == Fraction(1, 3)
    broken = make_tree(tmp_path / "b", {"main.c": "int main(void) { return }\n"})
    assert g("s3", broken).score == dq.BuildError()


#
# c-make
#
MAKEFILE = """\
run_tests: tests/test_calc.c calc.c
\t$(CC) $(CFLAGS) -I. -o $@ $^ $(LDFLAGS)
"""

C_TESTS = """\
#include "chalk_test.h"
#include "calc.h"

TEST(add) { CHECK_EQ(add(1, 2), 3); }
TEST(add_zero) { CHECK(add(0, 0) == 0); }
TEST(sub) { CHECK_EQ(sub(3, 2), 1); }
TEST(name) { CHECK_STREQ(name(), "calc"); }
"""

CALC_H = "int add(int a, int b);\nint sub(int a, int b);\nconst char *name(void);\n"


@pytest.fixture
def c_template(tmp_path: Path) -> Path:
    files = {"Makefile": MAKEFILE, "tests/test_calc.c": C_TESTS, "calc.h": CALC_H}
    return make_tree(tmp_path / "q" / "template", files)


def calc(add: str = "a + b", sub: str = "a - b", extra: str = "") -> dict[str, str]:
    body = (
        f'#include "calc.h"\n#include <stddef.h>\n{extra}\n'
        f"int add(int a, int b) {{ return {add}; }}\n"
        f"int sub(int a, int b) {{ return {sub}; }}\n"
        'const char *name(void) { return "calc"; }\n'
    )
    return {"calc.c": body}


@pytest.mark.skipif(not (shutil.which("cc") and shutil.which("make")), reason="cc, make needed")
@pytest.mark.parametrize("sandbox", SANDBOXES)
class TestCMake:
    def test_scores(self, c_template, tmp_path, sandbox) -> None:
        solution = make_tree(tmp_path / "sol", calc())
        g = grader("c-make", c_template, solution, sandbox=sandbox)
        assert g("s1", solution).score == 1

        graded = g("s2", make_tree(tmp_path / "s", calc(sub="0")))
        assert graded.score == Fraction(3, 4)
        assert "c::sub: tests/test_calc.c:6: sub(3, 2) == 1: 0 != 1" in (graded.feedback or "")

    def test_crash_and_loop_fail_one_test(self, c_template, tmp_path, sandbox) -> None:
        solution = make_tree(tmp_path / "sol", calc())
        g = grader("c-make", c_template, solution, sandbox=sandbox)
        crash = "*(volatile int *)NULL = a"
        graded = g("s1", make_tree(tmp_path / "s", calc(add=f"({crash}, a + b)")))
        assert graded.score == Fraction(2, 4)

        loop = calc(sub="spin(a)", extra="static int spin(int a) { for (;;) {} return a; }")
        g = grader("c-make", c_template, solution, sandbox=sandbox, vars={"test_timeout": "1"})
        graded = g("s2", make_tree(tmp_path / "l", loop))
        assert graded.score == Fraction(3, 4)
        assert "c::sub: timed out after 1s" in (graded.feedback or "")

    def test_student_makefile_is_replaced(self, c_template, tmp_path, sandbox) -> None:
        solution = make_tree(tmp_path / "sol", calc())
        fake = "run_tests:\n\tprintf '#!/bin/sh\\n' > run_tests; chmod +x run_tests\n"
        root = make_tree(tmp_path / "s", {**calc(sub="0"), "Makefile": fake})
        assert grader("c-make", c_template, solution, sandbox=sandbox)(
            "s1", root
        ).score == Fraction(3, 4)

    def test_build_error(self, c_template, tmp_path, sandbox) -> None:
        solution = make_tree(tmp_path / "sol", calc())
        broken = make_tree(tmp_path / "s", {"calc.c": "int add(int a, int b) { return a + }"})
        graded = grader("c-make", c_template, solution, sandbox=sandbox)("s1", broken)
        assert graded.score == dq.BuildError()
        assert "error" in (graded.feedback or "")


#
# elm-test
#
ELM_JSON = """{
    "type": "application",
    "source-directories": ["src"],
    "elm-version": "%s",
    "dependencies": {
        "direct": {"elm/core": "1.0.5", "elm/json": "1.1.3"},
        "indirect": {}
    },
    "test-dependencies": {
        "direct": {"elm-explorations/test": "2.2.1"},
        "indirect": {
            "elm/bytes": "1.0.8",
            "elm/html": "1.0.1",
            "elm/random": "1.0.0",
            "elm/time": "1.0.0",
            "elm/virtual-dom": "1.0.5"
        }
    }
}
"""

ELM_TESTS = """\
module CalcTest exposing (suite)

import Calc exposing (add, sub)
import Expect
import Test exposing (Test, describe, test)

suite : Test
suite =
    describe "Calc"
        [ test "add" <| \\_ -> Expect.equal 3 (add 1 2)
        , test "sub" <| \\_ -> Expect.equal 1 (sub 3 2)
        , describe "more" [ test "add zero" <| \\_ -> Expect.equal 0 (add 0 0) ]
        ]
"""


def elm_calc(sub: str = "a - b") -> dict[str, str]:
    return {
        "src/Calc.elm": "module Calc exposing (add, sub)\n\n"
        "add : Int -> Int -> Int\nadd a b = a + b\n\n"
        f"sub : Int -> Int -> Int\nsub a b = {sub}\n"
    }


@pytest.fixture
def elm_template(tmp_path: Path) -> Path:
    import subprocess

    version = subprocess.run(["elm", "--version"], capture_output=True, text=True).stdout.strip()
    files = {"elm.json": ELM_JSON % version, "tests/CalcTest.elm": ELM_TESTS}
    return make_tree(tmp_path / "q" / "template", files)


@pytest.mark.skipif(
    not (shutil.which("elm") and shutil.which("elm-test")), reason="elm and elm-test needed"
)
@pytest.mark.parametrize("sandbox", SANDBOXES)
def test_elm(elm_template, tmp_path, sandbox, tmp_path_factory) -> None:
    solution = make_tree(tmp_path / "sol", elm_calc())
    cache = tmp_path_factory.getbasetemp() / "elm-cache"
    g = grader("elm-test", elm_template, solution, cache, sandbox=sandbox)
    try:
        g.prepare()
    except PrepareError as e:
        # Packages come from package.elm-lang.org and GitHub; elm does not
        # retry, so a DNS hiccup fails the download.
        if any(m in str(e) for m in ("package.elm-lang.org", "PROBLEM DOWNLOADING")):
            pytest.skip(f"cannot download the elm packages: {e}")
        raise
    assert g("s1", solution).score == 1

    graded = g("s2", make_tree(tmp_path / "s", elm_calc(sub="0")))
    assert graded.score == Fraction(2, 3)
    assert "CalcTest Calc::sub: 1 was not equal to 0" in (graded.feedback or "")
    assert graded.cases is not None
    failed = [c.key for c in graded.cases if not c.passed]
    assert failed == [("CalcTest Calc", "sub")]

    broken = make_tree(tmp_path / "b", elm_calc(sub="a -"))
    assert g("s3", broken).score == dq.BuildError()

    # Each element is a list of its own, so the memory runs out long before
    # the time does.
    greedy = make_tree(
        tmp_path / "g",
        elm_calc(sub="List.length (List.map List.singleton (List.range 1 100000000))"),
    )
    if cgroup.controller() is None:
        # The heap of node stops it, and elm-test writes no report.
        assert g("s4", greedy).score == dq.Error()
    else:
        # With the heap of node far above the memory of the run, the cgroup
        # stops it first. With the heap at the memory of the run, as by
        # default, either may come first.
        env = {**g.spec.env, "NODE_OPTIONS": "--max-old-space-size=4096"}
        large_heap = replace(g, profile=g.spec.model_copy(update={"env": env}))
        assert large_heap("s4", greedy).score == dq.MemoryLimit()


def test_limits_set_the_memory_of_the_step() -> None:
    variables = {"memory_mib": "512", "jobs": "1"}
    assert with_limits(variables, None) == variables
    assert with_limits(variables, models.Limits()) == variables
    limits = models.Limits(memory="1GiB")
    assert with_limits(variables, limits) == {"memory_mib": "1024", "jobs": "1"}


def test_step_memory() -> None:
    assert step_memory({"memory_mib": "512"}) == 512 * 2**20
    assert step_memory({}) is None
    for wrong in ("1G", "0", "", "1.5"):
        with pytest.raises(PrepareError, match="whole number of MiB"):
            step_memory({"memory_mib": wrong})


class TestMemoryOfTheSteps:
    """The memory.max of the cgroup of each step."""

    run = {"run": "python3 main.py"}

    def test_profile_default(self, stdio_template, tmp_path, fake_cgroups) -> None:
        fake = fake_cgroups()
        solution = make_tree(tmp_path / "sol", {"main.py": "print(sum(map(int, input().split())))"})
        g = grader("stdio", stdio_template, solution, sandbox="none", vars=self.run)
        assert g("s1", solution).score == 1
        assert fake.created and {m for m, _ in fake.created} == {512 * 2**20}

    def test_vars(self, stdio_template, tmp_path, fake_cgroups) -> None:
        fake = fake_cgroups()
        solution = make_tree(tmp_path / "sol", {"main.py": "print(sum(map(int, input().split())))"})
        variables = {**self.run, "memory_mib": "300"}
        g = grader("stdio", stdio_template, solution, sandbox="none", vars=variables)
        assert g("s1", solution).score == 1
        assert {m for m, _ in fake.created} == {300 * 2**20}

    @pytest.mark.skipif(not shutil.which("cc"), reason="cc is needed")
    def test_limits_of_build_and_test(self, stdio_template, tmp_path, fake_cgroups) -> None:
        fake = fake_cgroups()
        c_sum = '#include <stdio.h>\nint main(void) { int a, b; scanf("%d %d", &a, &b); '
        c_sum += 'printf("%d\\n", a + b); }\n'
        solution = make_tree(tmp_path / "sol", {"main.c": c_sum})
        limits = models.Limits(memory="200MiB", processes=10)
        g = grader("c-stdio", stdio_template, solution, sandbox="none", limits=limits)
        assert g("s1", solution).score == 1
        # Reference and student, build and test.
        assert fake.created == [(200 * 2**20, 10)] * 4

    def test_invalid_memory_mib(self, stdio_template, tmp_path) -> None:
        solution = make_tree(tmp_path / "sol", {"main.py": "print(0)"})
        variables = {**self.run, "memory_mib": "1G"}
        g = grader("stdio", stdio_template, solution, sandbox="none", vars=variables)
        with pytest.raises(PrepareError, match="whole number of MiB"):
            g.prepare()
