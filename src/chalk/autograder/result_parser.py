import json
import re
from fractions import Fraction
from logging import getLogger

import opt

from ..core.grader import Graded
from .result_extractor import extract_from_primitive, extract_from_text

PYTEST_START = re.compile(r"=+ test session starts =+")
PYTEST_SUMMARY = re.compile(r"=+ short test summary info =+")
PYTEST_CONCLUSION = re.compile(r"=+ (?P<conclusion>(\d+ \w+,?\s*)+) in (?:[\d\.]+)s =+")
PASSED = re.compile(r"(\d+) passed")
FAILED = re.compile(r"(\d+) failed")
ERROR = re.compile(r"(\d+) error")
log = getLogger("chalk.autograder")


def parse_result_from_stdout(src: str) -> Graded | None:
    """
    Parse the result of the script execution from the stdout output.
    """
    result = None

    # Try parsing result as JSON
    try:
        data = json.loads(src)
    except json.JSONDecodeError:
        pass
    else:
        return extract_from_primitive(data)

    # Look for a line that starts with "RESULT: " and parse the JSON after it
    for i, line in enumerate(lines := src.splitlines()):
        if line.startswith("CHALK_RESULT"):
            head = line.removeprefix("CHALK_RESULT").removeprefix(":").strip()
            tail = "\n".join(lines[i + 1 :])
            result = extract_from_text(f"{head}\n{tail}".lstrip("\n"))
            break

    if result is None:
        result = parse_pytest_outcome(src)

    return result


def parse_pytest_outcome(src: str) -> Graded | None:
    """
    Parse the result of the script execution from the stdout output.
    """
    if not (start := PYTEST_START.search(src)):
        return None

    idx = start.end()
    if summary := PYTEST_SUMMARY.search(src, pos=idx):
        idx = summary.end()

    if start and (m := PYTEST_CONCLUSION.search(src, pos=idx)):
        conclusion = m.group("conclusion")

        passed = opt.map(lambda x: int(x.group(1)), PASSED.search(conclusion)) or 0
        failed = opt.map(lambda x: int(x.group(1)), FAILED.search(conclusion)) or 0
        error = opt.map(lambda x: int(x.group(1)), ERROR.search(conclusion)) or 0
        log.info(f"pytest: passed: {passed}, failed: {failed + error}")

        feedback = []
        if passed:
            feedback.append(f"{passed} passed")
        if failed:
            feedback.append(f"{failed} failed")
        if error:
            feedback.append(f"{error} error")

        feedback_msg = None
        if len(feedback) > 1:
            feedback_msg = ", ".join(feedback)

        return Graded(
            score=Fraction(passed, passed + failed + error),
            feedback=feedback_msg,
        )
    return None
