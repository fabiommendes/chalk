"""
The prolog-plunit profile: plunit tests from the template run against a
student's Prolog file, one swipl process per test, with the student's program
checked by safe_goal/1 of library(sandbox) before anything runs.

The fixture is the real question `prolog-fatorial-com-is`: `fat(5, F)` gives
`F = 120`, and `fat(X, 120)` must not give `X = 5` (failing and raising an
instantiation error both pass).
"""

import shutil
import time
from fractions import Fraction
from pathlib import Path

import pytest

from chalk.core import disqualification as dq
from tests.test_autograder_more_profiles import grader, make_tree
from tests.test_autograder_sandbox import needs_bwrap

needs_swipl = pytest.mark.skipif(not shutil.which("swipl"), reason="swipl is needed")
SANDBOXES = ["none", pytest.param("bwrap", marks=needs_bwrap)]

pytestmark = needs_swipl

TESTS = """\
:- begin_tests(fatorial).
test(fat5) :- fat(5, F), F == 120.
test(inverso) :- \\+ catch((fat(X, 120), X == 5), _, fail).
:- end_tests(fatorial).
"""

CORRECT = """\
fat(0,1).
fat(N,F):- N > 0, N1 is N-1, fat(N1,F1), F is N*F1.
"""

#: Never gives 120, but does not give X = 5 either.
WRONG = "fat(_, 1).\n"

#: Right for fat(5, F), but fat(X, 120) gives X = 5.
REVERSIBLE = "fat(5, 120).\nfat(X, 120) :- X = 5.\n"

#: Loops forever on fat(5, F) only.
LOOP = "fat(N, _) :- N == 5, repeat, fail.\n" + CORRECT

#: Both tests need the whole file to load, so they are all-or-nothing here.
NOT_LOADING = "fat(0,1\nfat(N,F) :- .\n"


@pytest.fixture
def template(tmp_path: Path) -> Path:
    return make_tree(tmp_path / "q" / "template", {"tests.pl": TESTS})


def prolog(template: Path, answer: str, sandbox: str = "none", **conf):
    vars = {"test_timeout": "1", **conf.pop("vars", {})}
    g = grader(
        "prolog-plunit",
        template,
        CORRECT,  # type: ignore[arg-type]
        sandbox=sandbox,
        answer="answer.pl",
        vars=vars,
        **conf,
    )
    return g("s1", answer)


@pytest.mark.parametrize("sandbox", SANDBOXES)
class TestScores:
    def test_correct_answer_gets_full_score(self, template, sandbox) -> None:
        graded = prolog(template, CORRECT, sandbox)
        assert graded.score == Fraction(1)
        assert not graded.notes

    def test_wrong_answer_loses_the_failing_test_only(self, template, sandbox) -> None:
        graded = prolog(template, WRONG, sandbox)
        assert graded.score == Fraction(1, 2)
        assert "fat5" in graded.feedback
        assert "inverso" not in graded.feedback

    def test_reversible_answer_fails_the_inverse_test(self, template, sandbox) -> None:
        graded = prolog(template, REVERSIBLE, sandbox)
        assert graded.score == Fraction(1, 2)
        assert "inverso" in graded.feedback
        assert "fat5" not in graded.feedback

    def test_infinite_loop_fails_only_that_test(self, template, sandbox) -> None:
        start = time.monotonic()
        graded = prolog(template, LOOP, sandbox)
        assert graded.score == Fraction(1, 2)
        assert "fat5" in graded.feedback
        assert time.monotonic() - start < 30

    def test_code_that_does_not_load_is_a_build_error(self, template, sandbox) -> None:
        graded = prolog(template, NOT_LOADING, sandbox)
        assert graded.score == dq.BuildError()
        assert graded.feedback


class TestUnsafeCode:
    """
    Programs refused by safe_goal/1 never run: build-error, and the list of
    what was refused goes to the notes, never to the feedback.
    """

    @pytest.mark.parametrize(
        ("code", "words"),
        [
            pytest.param(
                CORRECT + ":- initialization(halt(0)).\n", ("halt", "initialization"), id="init"
            ),
            pytest.param(CORRECT + ":- halt.\n", ("halt",), id="directive-halt"),
            pytest.param("fat(N, F) :- N == 5, halt, F = 1.\n" + CORRECT, ("halt",), id="body"),
            pytest.param("fat(0, 1) :- shell('id').\n" + CORRECT, ("shell",), id="shell"),
            pytest.param(
                "fat(N, F) :- open('/etc/passwd', read, S), read(S, F), N = 1.\n" + CORRECT,
                ("open",),
                id="open-file",
            ),
        ],
    )
    def test_is_refused(self, template, code, words) -> None:
        graded = prolog(template, code)
        assert graded.score == dq.BuildError()
        assert graded.notes
        assert any(w in graded.notes for w in words), graded.notes
        assert graded.notes not in (graded.feedback or "")

    def test_clause_that_is_never_called_is_still_refused(self, template) -> None:
        graded = prolog(template, CORRECT + "unused :- shell(true).\n")
        assert graded.score == dq.BuildError()

    def test_safe_off_allows_it(self, template) -> None:
        graded = prolog(template, CORRECT + "unused :- shell(true).\n", vars={"safe": "off"})
        assert graded.score == Fraction(1)

    def test_halt_kills_only_its_own_test_when_unsafe_code_is_allowed(self, template) -> None:
        code = "fat(N, _) :- N == 5, halt.\n" + CORRECT
        graded = prolog(template, code, vars={"safe": "off"})
        assert graded.score == Fraction(1, 2)
        assert "fat5" in graded.feedback


class TestForgery:
    """
    A wrong program that pretends to pass cannot get more than an honest
    wrong one. Being refused (build-error) is as good as being neutralized.
    """

    FORGERIES = {
        "fake-output": (
            WRONG
            + ':- format("% All 2 tests passed~n").\n'
            + ':- format("[1/2] fatorial:fat5 ..... passed~n").\n'
        ),
        "own-plunit-unit": (
            WRONG
            + ":- begin_tests(fatorial).\n"
            + "test(fat5) :- true.\ntest(inverso) :- true.\n"
            + ":- end_tests(fatorial).\n"
        ),
        "own-run-tests": WRONG + 'run_tests :- format("All 2 tests passed~n").\n',
        "plunit-module": WRONG + "plunit:run_tests :- true.\n",
        "plunit-run-tests-1": WRONG + "plunit:run_tests(_) :- true.\n",
        "user-test-predicate": WRONG + "user:test(_) :- true.\n",
    }

    @pytest.mark.parametrize("name", FORGERIES)
    def test_forged_pass_does_not_raise_the_score(self, template, name) -> None:
        graded = prolog(template, self.FORGERIES[name])
        assert graded.score in (Fraction(1, 2), dq.BuildError()), graded


def test_bot_key_is_not_visible_to_the_student_program(template, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEHOOD_BOT_KEY", "secret-key")
    tests = ":- begin_tests(env).\ntest(nokey) :- \\+ getenv('CODEHOOD_BOT_KEY', _).\n"
    tests += ":- end_tests(env).\n"
    template = make_tree(tmp_path / "k" / "template", {"tests.pl": tests})
    graded = prolog(template, "fat(0, 1).\n", vars={"safe": "off"})
    assert graded.score == Fraction(1)
