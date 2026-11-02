from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from chalk.autograder.repo import Repo
from chalk.autograder.result_extractor import extract_result_from_file
from chalk.autograder.script_runner import ChalkEnv, ScriptRunner
from chalk.core import disqualification as dq

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="4">
    <testcase classname="tests.test_a" name="test_ok"/>
    <testcase classname="tests.test_a" name="test_fail"><failure message="x"/></testcase>
    <testcase classname="tests.test_a" name="test_error"><error message="y"/></testcase>
    <testcase classname="tests.test_a" name="test_skip"><skipped/></testcase>
  </testsuite>
</testsuites>
"""


def run_script(tmp_path: Path, body: str):
    script = tmp_path / "grade.sh"
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    env = ChalkEnv(
        answer="x", answer_path="answer.txt", question_id="q1", quiz_id="p1", student_id="s1"
    )
    return ScriptRunner(script, Repo(work), env=env, timeout=5).run(), work


def extract(tmp_path: Path, content: str):
    path = tmp_path / "result"
    path.write_text(content)
    return extract_result_from_file(path)


class TestFormats:
    @pytest.mark.parametrize(
        "content, expected",
        [
            ("0.8\n", Decimal("0.8")),
            ("80%\n", Decimal("0.8")),
            ("3/4\n", Fraction(3, 4)),
            ('{"score": 0.5}', Decimal("0.5")),
            ('{"pass": 1, "fail": 3}', Fraction(1, 4)),
        ],
    )
    def test_score(self, tmp_path, content, expected) -> None:
        assert extract(tmp_path, content).score == expected

    def test_text_feedback_follows_score(self, tmp_path) -> None:
        graded = extract(tmp_path, "3/4\nFaltou o caso x=0.\n")
        assert graded.feedback == "Faltou o caso x=0."

    def test_junit(self, tmp_path) -> None:
        graded = extract(tmp_path, JUNIT)
        assert graded.score == Fraction(1, 3)
        assert "tests.test_a.test_fail" in graded.feedback
        assert "tests.test_a.test_error" in graded.feedback
        assert "test_skip" not in graded.feedback

    def test_junit_single_testsuite_root(self, tmp_path) -> None:
        src = '<testsuite><testcase name="a"/><testcase name="b"/></testsuite>'
        assert extract(tmp_path, src).score == 1

    def test_invalid_junit(self, tmp_path) -> None:
        assert extract(tmp_path, "<testsuite>").score == dq.Error()

    def test_empty_result(self, tmp_path) -> None:
        assert extract(tmp_path, "").score == dq.Error()


class TestRunner:
    def test_result_file_is_outside_working_directory(self, tmp_path) -> None:
        _, work = run_script(
            tmp_path, 'echo "$CHALK_RESULT" > where.txt\necho 1 > "$CHALK_RESULT"\n'
        )
        where = Path((work / "where.txt").read_text().strip())
        assert where.is_absolute()
        assert work not in where.parents

    def test_result_is_kept_for_inspection(self, tmp_path) -> None:
        _, work = run_script(tmp_path, 'echo 3/4 > "$CHALK_RESULT"\n')
        assert (work / "chalk.result").read_text() == "3/4\n"

    def test_stdout_is_not_parsed(self, tmp_path) -> None:
        result, _ = run_script(tmp_path, "echo 'CHALK_RESULT: 1'\n")
        assert result.score == dq.Error()

    def test_pytest_summary_in_stdout_is_not_parsed(self, tmp_path) -> None:
        body = "echo '===== test session starts ====='\necho '===== 5 passed in 0.1s ====='\n"
        result, _ = run_script(tmp_path, body)
        assert result.score == dq.Error()

    def test_score_from_result_file(self, tmp_path) -> None:
        result, _ = run_script(
            tmp_path, 'echo "Ignored: CHALK_RESULT: 0"\necho 3/4 > "$CHALK_RESULT"\n'
        )
        assert result.score == Fraction(3, 4)
