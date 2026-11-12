import time
from fractions import Fraction
from pathlib import Path

import pytest

from chalk.autograder.regex_answer import RegexAnswerGrader
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
        # Keep the classroom alive: questions hold only weak references to it.
        room = Classroom.load()
        grader = room.get_quiz("p1").get_question("q3").get_grader()
        assert isinstance(grader, RegexAnswerGrader)
        assert grader("s1", "ab[c]").score == 1
