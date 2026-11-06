"""
The `scoring` key of the autograder: proportional (default), all-or-nothing
and a teacher script.

The prolog-plunit profile with the factorial fixture gives a wrong answer
that passes 1 of the 2 tests.
"""

import json
import shutil
from fractions import Fraction
from pathlib import Path

import pydantic
import pytest

from chalk.autograder import scoring
from chalk.autograder.profiles import score_report
from chalk.core import disqualification as dq
from chalk.core import models
from tests.test_autograder_more_profiles import grader, make_tree
from tests.test_autograder_prolog import CORRECT, TESTS, WRONG

needs_swipl = pytest.mark.skipif(not shutil.which("swipl"), reason="swipl is needed")

JUNIT = """\
<testsuite>
  <testcase classname="c" name="a"/>
  <testcase classname="c" name="b"><failure message="boom"/></testcase>
</testsuite>
"""
EXPECTED = {("c", "a"): "c::a", ("c", "b"): "c::b", ("c", "missing"): "c::missing"}

#: Dumps its input next to itself and gives 1/4.
DUMP = """\
import json, pathlib, sys
data = json.load(sys.stdin)
pathlib.Path(__file__).with_name("input.json").write_text(json.dumps(data))
print("1/4")
"""


def prolog(tmp_path: Path, answer: str, files: dict[str, str] | None = None, **conf):
    template = make_tree(tmp_path / "q" / "template", {"tests.pl": TESTS})
    make_tree(tmp_path / "q", files or {})
    vars = {"test_timeout": "1"}
    g = grader(
        "prolog-plunit",
        template,
        CORRECT,
        sandbox="none",
        answer="answer.pl",
        vars=vars,
        **conf,  # type: ignore[arg-type]
    )
    return g("s1", answer)


class TestConfig:
    def test_default_is_proportional(self) -> None:
        conf = models.Autograder()
        assert conf.scoring == "proportional"
        assert conf.scoring_script is None

    def test_script_scoring_needs_the_script(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="scoring_script"):
            models.Autograder(scoring="script")

    @pytest.mark.parametrize("scoring", ["proportional", "all-or-nothing"])
    def test_script_without_script_scoring_is_an_error(self, scoring) -> None:
        with pytest.raises(pydantic.ValidationError, match="scoring_script"):
            models.Autograder(scoring=scoring, scoring_script="s.py")

    def test_valid_script_scoring(self) -> None:
        conf = models.Autograder(scoring="script", scoring_script="s.py")
        assert conf.scoring_script == Path("s.py")


class TestReport:
    def test_scorer_gets_every_expected_test_and_missing_ones_fail(self) -> None:
        seen = []

        def scorer(tests, expected):
            seen.append((tests, expected))
            return Fraction(1, 5)

        graded = score_report(JUNIT, EXPECTED, scorer=scorer)
        assert graded.score == Fraction(1, 5)
        ((tests, expected),) = seen
        assert expected == ["c::a", "c::b", "c::missing"]
        assert [(t["name"], t["passed"]) for t in tests] == [
            ("c::a", True),
            ("c::b", False),
            ("c::missing", False),
        ]
        assert tests[0]["message"] is None
        assert "boom" in tests[1]["message"]

    def test_feedback_does_not_change(self) -> None:
        plain = score_report(JUNIT, EXPECTED)
        scored = score_report(JUNIT, EXPECTED, scorer=scoring.all_or_nothing)
        assert scored.feedback == plain.feedback
        assert plain.score == Fraction(1, 3)
        assert scored.score == 0

    def test_scoring_error_is_an_infrastructure_error(self) -> None:
        def scorer(tests, expected):
            raise scoring.ScoringError("it broke")

        graded = score_report(JUNIT, EXPECTED, scorer=scorer)
        assert graded.score == dq.Error()
        assert "it broke" in graded.feedback


class TestScriptScorer:
    def run(self, tmp_path: Path, source: str, **kw):
        path = tmp_path / "score.py"
        path.write_text(source)
        tests = [{"name": "t", "passed": True, "message": None}]
        return scoring.ScriptScorer(path, **kw)(tests, ["t"])

    @pytest.mark.parametrize(
        ("out", "value"),
        [
            ("0.25", Fraction(1, 4)),
            ("1/3\n", Fraction(1, 3)),
            ("1", 1),
            ("0", 0),
            (".5", Fraction(1, 2)),
        ],
    )
    def test_accepts_decimal_and_fraction(self, tmp_path, out, value) -> None:
        assert self.run(tmp_path, f"print({out!r})") == value

    @pytest.mark.parametrize(
        "out", ["1.5", "-0.1", "3/2", "1/0", "abc", "", "nan", "0.5 0.5", "1e0"]
    )
    def test_bad_output_is_an_error(self, tmp_path, out) -> None:
        with pytest.raises(scoring.ScoringError):
            self.run(tmp_path, f"print({out!r})")

    def test_exit_code_and_stderr(self, tmp_path) -> None:
        src = "import sys\nsys.stderr.write('teacher bug')\nsys.exit(3)"
        with pytest.raises(scoring.ScoringError, match="teacher bug"):
            self.run(tmp_path, src)

    def test_timeout(self, tmp_path) -> None:
        with pytest.raises(scoring.ScoringError, match="timed out"):
            self.run(tmp_path, "import time\ntime.sleep(30)", timeout=0.5)

    def test_missing_script(self, tmp_path) -> None:
        with pytest.raises(scoring.ScoringError, match="nope.py"):
            scoring.ScriptScorer(tmp_path / "nope.py")([], [])


@needs_swipl
class TestProfile:
    def test_proportional_is_the_default(self, tmp_path) -> None:
        graded = prolog(tmp_path, WRONG)
        assert graded.score == Fraction(1, 2)

    def test_all_or_nothing_gives_zero_to_a_half_right_answer(self, tmp_path) -> None:
        graded = prolog(tmp_path, WRONG, scoring="all-or-nothing")
        assert graded.score == 0
        assert "fat5" in graded.feedback
        assert "inverso" not in graded.feedback

    def test_all_or_nothing_gives_one_to_a_right_answer(self, tmp_path) -> None:
        assert prolog(tmp_path, CORRECT, scoring="all-or-nothing").score == 1

    def test_script_decides_the_score(self, tmp_path) -> None:
        graded = prolog(
            tmp_path,
            WRONG,
            {"score.py": DUMP},
            scoring="script",
            scoring_script="score.py",
        )
        assert graded.score == Fraction(1, 4)
        assert "fat5" in graded.feedback
        sent = json.loads((tmp_path / "q" / "input.json").read_text())
        assert len(sent["expected"]) == 2
        by_name = {t["name"]: t["passed"] for t in sent["tests"]}
        assert sorted(by_name.values()) == [False, True]
        assert [t["name"] for t in sent["tests"]] == sent["expected"]

    def test_failing_script_is_an_error_with_its_stderr(self, tmp_path) -> None:
        src = "import sys\nsys.stderr.write('bad teacher')\nsys.exit(1)"
        graded = prolog(
            tmp_path, WRONG, {"score.py": src}, scoring="script", scoring_script="score.py"
        )
        assert graded.score == dq.Error()
        assert "bad teacher" in graded.feedback
