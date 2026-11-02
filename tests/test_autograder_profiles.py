import time
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from chalk.autograder.regex_answer import RegexAnswerGrader
from chalk.autograder.script_grader import ScriptGrader
from chalk.core import Classroom, models
from chalk.core import disqualification as dq

EMAILS = models.Autograder(
    profile="regex",
    match=["ana@unb.br", "x.y@a.com"],
    reject=["@unb.br", "ana@"],
)


class TestRegexProfile:
    def test_correct_regex(self) -> None:
        graded = RegexAnswerGrader(EMAILS)("s1", r"[\w.]+@[\w.]+" + "\n")
        assert graded.score == 1
        assert graded.feedback is None

    def test_partial_score_lists_wrong_examples(self) -> None:
        graded = RegexAnswerGrader(EMAILS)("s1", ".*")
        assert graded.score == Fraction(2, 4)
        assert "should not match '@unb.br'" in graded.feedback

    def test_invalid_regex(self) -> None:
        graded = RegexAnswerGrader(EMAILS)("s1", "(")
        assert graded.score == 0
        assert graded.feedback.startswith("Invalid regex")

    def test_search_mode(self) -> None:
        conf = EMAILS.model_copy(update={"regex_mode": "search"})
        assert RegexAnswerGrader(conf)("s1", "@").score == Fraction(2, 4)

    def test_catastrophic_backtracking_fails_only_that_example(self) -> None:
        conf = models.Autograder(profile="regex", match=["aa"], reject=["a" * 40 + "!", "b"])
        start = time.time()
        graded = RegexAnswerGrader(conf, example_timeout=0.3)("s1", "(a+)+")
        assert time.time() - start < 3
        assert graded.score == Fraction(2, 3)
        assert "took too long" in graded.feedback

    def test_needs_examples(self) -> None:
        with pytest.raises(ValueError, match="examples"):
            RegexAnswerGrader(models.Autograder(profile="regex"))

    def test_answer_too_large(self) -> None:
        conf = EMAILS.model_copy(update={"limits": models.Limits(answer_size=10)})
        assert RegexAnswerGrader(conf)("s1", "a" * 11).score == dq.InvalidInput()

    def test_question_uses_profile(self, classroom: Path) -> None:
        conf = classroom / "p1" / "conf.yaml"
        entry = (
            "  - id: q3\n    autograder:\n      profile: regex\n"
            "      match: [abc]\n      reject: [abd]\n"
        )
        conf.write_text(conf.read_text().replace("  - id: q3\n", entry))
        grader = Classroom.load().get_quiz("p1").get_question("q3").get_grader()
        assert isinstance(grader, RegexAnswerGrader)
        assert grader("s1", "ab[c]").score == 1


def script_grader(tmp_path: Path, body: str, **conf) -> ScriptGrader:
    script = tmp_path / "grade.sh"
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(0o755)
    question = SimpleNamespace(
        id="q1", quiz=SimpleNamespace(id="p1"), get_template_path=lambda: None
    )
    return ScriptGrader(script, question, models.Autograder(**conf))  # type: ignore[arg-type]


class TestScriptLimits:
    def test_timeout_from_conf(self, tmp_path) -> None:
        grader = script_grader(tmp_path, "sleep 10\n", timeout=0.3)
        start = time.time()
        assert grader("s1", "x").score == dq.Timeout()
        assert time.time() - start < 5

    def test_answer_too_large(self, tmp_path) -> None:
        grader = script_grader(
            tmp_path, 'echo 1 > "$CHALK_RESULT"\n', limits={"answer_size": "10B"}
        )
        assert grader("s1", "x" * 11).score == dq.InvalidInput()
        assert grader("s1", "x" * 10).score == 1

    def test_file_size(self, tmp_path) -> None:
        body = 'head -c 100000 /dev/zero > big\nwc -c < big > "$CHALK_RESULT"\n'
        grader = script_grader(tmp_path, body, limits={"file_size": "1KB"})
        graded = grader("s1", "x", keep_files=True)
        assert graded.score <= 1000

    def test_memory(self, tmp_path) -> None:
        body = (
            "python3 -c 'b = bytearray(400_000_000)' && echo 1 > \"$CHALK_RESULT\""
            ' || echo 0 > "$CHALK_RESULT"\n'
        )
        grader = script_grader(tmp_path, body, limits={"memory": "200MB"})
        assert grader("s1", "x").score == 0

    def test_sandbox_not_implemented(self, tmp_path) -> None:
        grader = script_grader(tmp_path, 'echo 1 > "$CHALK_RESULT"\n', sandbox="bwrap")
        with pytest.raises(NotImplementedError, match="bwrap"):
            grader("s1", "x")
