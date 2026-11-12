from __future__ import annotations

import itertools
import json
import xml.etree.ElementTree as ET
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from functools import lru_cache
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import disqualification as dq
from . import score
from .graded import Graded

log = getLogger("chalk.autograder")

type JSON = dict[str, Any] | list[Any] | str | int | float | bool | None

if TYPE_CHECKING:
    Number = float
else:
    Number = int | float

__all__ = [
    "extract_result_from_file",
]

#: Larger result files are rejected instead of parsed.
MAX_RESULT_SIZE = 10 * 1024 * 1024


def extract_result_from_file(path: Path, /) -> Graded:
    """
    Extract the score and feedback from the given result file.

    The format is detected from the content: JUnit XML (starts with "<"),
    JSON, or plain text with the score in the first line and the feedback in
    the others.
    """
    if path.stat().st_size > MAX_RESULT_SIZE:
        return Graded(dq.Error(), feedback="Grading result is too large.")
    src = path.read_text(errors="replace")
    if src.lstrip().startswith("<"):
        return extract_from_junit(src)
    return extract_from_text(src)


def extract_from_junit(src: str) -> Graded:
    """
    Extract the score from a JUnit XML report.

    The score is passed / (passed + failed + errors); skipped tests do not
    count. The feedback lists the tests that did not pass.
    """
    try:
        root = ET.fromstring(src)
    except ET.ParseError as e:
        return Graded(dq.Error(), feedback=f"Invalid JUnit report: {e}")

    passed = 0
    failed: list[str] = []
    for case in root.iter("testcase"):
        if case.find("skipped") is not None:
            continue
        name = ".".join(filter(None, [case.get("classname"), case.get("name")]))
        if case.find("failure") is not None or case.find("error") is not None:
            failed.append(name)
        else:
            passed += 1

    if passed + len(failed) == 0:
        return Graded(dq.Error(), feedback="no tests collected")
    feedback = "Failed tests:\n" + "\n".join(f"- {n}" for n in failed) if failed else None
    return Graded(Fraction(passed, passed + len(failed)), feedback=feedback)


def extract_from_text(src: str) -> Graded:
    """
    Extract the score and feedback from the given text string and update the
    response accordingly.

    The default format is: first line is the score and the rest is the feedback.
    """
    if src.strip() == "":
        return Graded(dq.Error(), feedback="Empty grading result.")

    clean_src = src.strip()
    try:
        data = json.loads(clean_src, parse_float=Decimal)
    except json.JSONDecodeError:
        if clean_src.startswith("{") or clean_src.startswith("["):
            log.warning("Invalid JSON format in result: %s", clean_src)
            return Graded(dq.Error(), feedback=clean_src)
    else:
        return extract_from_primitive(data)

    [score_data, *rest] = src.splitlines()
    feedback = "\n".join(rest).strip() or None
    score_data = score_data.strip().lower().removeprefix("score:").strip()

    if "/" in score_data:
        num, _, den = score_data.partition("/")
        try:
            value = Fraction(int(num), int(den))
        except (ValueError, ZeroDivisionError):
            log.warning("Invalid score format: %s", score_data)
            return Graded(dq.Error(), feedback=src)
        return Graded(value, feedback)
    elif score_data.endswith("%"):
        try:
            value = Decimal(score_data[:-1].strip()) / 100
        except ValueError:
            log.warning("Invalid score format: %s", score_data)
            return Graded(dq.Error(), feedback=src)
        else:
            return Graded(value, feedback)
    else:
        try:
            value = Decimal(score_data)
        except (ValueError, InvalidOperation):
            log.warning("Invalid score format: %s", score_data)
            return Graded(dq.Error(), feedback=src)
        else:
            return Graded(value, feedback)


def extract_from_primitive(data: JSON) -> Graded:
    """
    Extract the answer from the given data dictionary and update the response accordingly.

    This is a placeholder implementation. The actual extraction logic will depend on the structure of the data and how the answer is represented within it.
    """
    # Try atomic values
    if data is None:
        return Graded(dq.Error(), feedback="Empty grading result.")
    if isinstance(data, (int, float, Decimal)):
        return Graded(score.score(data, out_of_bound=True), feedback=None)

    if isinstance(data, dict):
        keys = tuple(sorted(data.keys()))
        valid_keys = get_valid_keys()
        keys = tuple(k for k in keys if k in valid_keys)

        if keys in FROM_DICT_IMPLEMENTATIONS:
            impl = FROM_DICT_IMPLEMENTATIONS[keys]
            try:
                return impl(data)
            except Exception as e:
                log.warning(f"Error extracting result from data: {e}")
                return Graded(dq.Error(), feedback=str(e))

    # We try processing some common types of structured data
    try:
        return read_pytest_report(data)
    except ValueError:
        pass

    raise RuntimeError(f"Could not extract result from data: {data}")


def read_pytest_report(data: JSON) -> Graded:
    """
    Extract the score and feedback from a pytest report.

    The report is expected to be a dictionary either the following structure:

    {
        summary: {
            passed: int,
            failed: int,
            error?: int,
            skipped?: int,
            collected?: int,
            xfailed?: int,
            xpassed?: int,
            total?: int,
        },
    }

    or the more complex:

    {
        tests: [
            {
                nodeid: str,
                outcome: str,
                metadata?: { score?: float | int, feedback?: str },
            },
            ...
        ],
    }

    The score is calculated as the number of passed tests divided by the total number of tests.
    """

    if not isinstance(data, dict):
        raise ValueError("Invalid pytest report format: expected a dictionary.")

    # Try the more complex structure first, looking for metadata
    if "tests" in data and isinstance(data["tests"], list):
        try:
            return read_pytest_report_with_metadata(data["tests"])
        except ValueError:
            pass

    # Test if keys values are ints
    summary = data.get("summary")
    if not isinstance(summary, dict) or not (set(map(type, summary.values())) == {int}):
        msg = "Invalid pytest report format: 'summary' must be a dictionary with integer values."
        raise ValueError(msg)

    if "collected" not in summary or "total" not in summary:
        raise ValueError("Invalid pytest summary.")

    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    error = summary.get("error", 0)

    # we don't use total to avoid confusion with xfailed, xpassed, etc.
    total = passed + failed + error

    if total == 0:
        return Graded(dq.Error(), feedback="no tests collected")
    return Graded(score=Fraction(passed, total), feedback=None)


def read_pytest_report_with_metadata(tests: list[dict[str, JSON]]) -> Graded:
    passed = 0.0
    missed = 0.0
    feedbacks: list[str] = []

    for index, item in enumerate(tests):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid pytest report at tests/{index}: not a dict.")

        nodeid = simplify_nodeid(_getchecked(item, "nodeid", str))
        outcome = _getchecked(item, "outcome", str)
        meta = item.get("metadata", {})
        if not isinstance(meta, dict):
            raise ValueError(f"Metadata section at tests/{index}: not a dict.")

        weight = _typecheck(meta.get("score", 1.0), Number)
        feedback = _typecheck(meta.get("feedback") or "", str) or None

        if outcome == "passed":
            passed += weight
        elif outcome in {"failed", "error"}:
            missed += weight
        else:
            # ignore xfailed, xpassed, skipped, etc.
            continue

        if feedback:
            feedbacks.append(f"[{nodeid}] {feedback}")

    feedback = "\n".join(feedbacks) if feedbacks else None
    total = passed + missed
    if total == 0:
        return Graded(dq.Error(), feedback="no tests collected")

    if int(passed) == passed and int(missed) == missed:
        # If all weights are integers, we can return a fraction
        return Graded(score=Fraction(int(passed), int(total)), feedback=feedback)

    return Graded(
        score=Decimal(passed / total),
        feedback=feedback,
    )


def simplify_nodeid(nodeid: str) -> str:
    _, _, nodeid = nodeid.partition("::")
    return nodeid


#
# Extractors
#
type DictConverter = Callable[[dict[str, JSON]], Graded]

FROM_DICT_IMPLEMENTATIONS: dict[tuple[str, ...], DictConverter] = {}


def dict_extractor(keys: tuple[str, ...]) -> Callable[[DictConverter], DictConverter]:
    """
    Decorator to register a function as an extractor for a specific set of keys.
    """

    def decorator(func: DictConverter) -> DictConverter:
        FROM_DICT_IMPLEMENTATIONS[tuple(sorted(keys))] = func
        return func

    return decorator


@dict_extractor(("score", "feedback"))
@dict_extractor(("score",))
def _(data: dict[str, JSON], /) -> Graded:
    value = data.get("score")
    feedback = data.get("feedback")
    if feedback is not None and not isinstance(feedback, str):
        raise ValueError("Invalid feedback format: must be a string.")
    feedback = feedback.strip() or None if feedback else None

    # Percentages, e.g. "80%"
    if isinstance(value, str) and value.strip().endswith("%"):
        try:
            percent = Decimal(value.strip().removesuffix("%").strip())
        except InvalidOperation:
            log.warning("Invalid score format: %s", value)
            return Graded(dq.Error(), feedback=feedback)
        return Graded(score.validate_score(percent / 100, out_of_bound=True), feedback=feedback)

    try:
        result = score.validate_score(value, out_of_bound=True)
    except (ValueError, TypeError):
        log.warning("Invalid score format: %s", value)
        return Graded(dq.Error(), feedback=feedback)
    return Graded(result, feedback=feedback)


@dict_extractor(("pass", "fail", "feedback"))
@dict_extractor(("pass", "fail"))
def _(data: dict[str, JSON], /) -> Graded:
    passed = _getchecked(data, "pass", int)
    failed = _getchecked(data, "fail", int)
    feedback = data.get("feedback")

    if feedback is not None and not isinstance(feedback, str):
        raise ValueError("Invalid feedback format: must be a string.")

    total = passed + failed
    if total == 0:
        return Graded(dq.Error(), feedback="no tests collected")

    return Graded(score=Fraction(passed, total), feedback=feedback)


@lru_cache
def get_valid_keys() -> frozenset[str]:
    keys = iter(FROM_DICT_IMPLEMENTATIONS.keys())
    return frozenset(itertools.chain(*keys))


def _typecheck[T](v: JSON, typ: type[T], /) -> T:
    if isinstance(v, typ):
        return v
    raise ValueError(f"Unexpected type: {type(v).__name__}")


def _getchecked[T](v: JSON, key: str, typ: type[T], /) -> T:
    if not isinstance(v, dict):
        raise ValueError("Expected a dictionary")
    return _typecheck(v.get(key), typ)
