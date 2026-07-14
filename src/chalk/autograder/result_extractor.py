from __future__ import annotations

import itertools
from decimal import Decimal
from fractions import Fraction
from functools import lru_cache
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ..core import disqualification as dq
from ..core import score
from ..core.grader import Graded
from ..core.score import validate_score
from ..data import load_structured_data
from ..numeric import to_decimal
from ..protocols import JSON

log = getLogger("chalk.autograder")

if TYPE_CHECKING:
    Number = float
else:
    Number = int | float

__all__ = [
    "extract_result_from_file",
]


def extract_result_from_file(path: Path, /) -> Graded:
    """
    Extract the score and feedback from the given result file and update the
    response accordingly.
    """
    if path.exists() and path.suffix in {".json", ".yaml", ".yml"}:
        data = load_structured_data(path)
        return extract_from_primitive(data)

    if path.exists() and path.suffix == ".txt":
        src = path.read_text()
        return extract_from_text(src)

    base = path.parent / path.stem
    for suffix in [".json", ".yaml", ".yml", ".txt", ""]:
        path = base.with_suffix(suffix)
        if path.exists():
            if suffix in {".json", ".yaml", ".yml"}:
                data = load_structured_data(path)
                return extract_from_primitive(data)
            elif suffix in {".txt", ""}:
                src = path.read_text()
                return extract_from_text(src)

    raise NotImplementedError("Could not extract result from {}.".format(path))


def extract_from_text(src: str) -> Graded:
    """
    Extract the score and feedback from the given text string and update the
    response accordingly.

    The default format is: first line is the score and the rest is the feedback.
    """
    if src.strip() == "":
        return Graded(dq.Error(), feedback="Empty grading result.")

    [score_data, *rest] = src.splitlines()
    feedback = "\n".join(rest).strip() or None
    score_data = score_data.strip().lower().removeprefix("score:").strip()

    if score_data.endswith("%"):
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
        except ValueError:
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
    if isinstance(data, (int, float)):
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

    raise RuntimeError("Could not extract result from data: {}".format(data))


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


@dict_extractor(("score", "max", "feedback"))
@dict_extractor(("score", "max"))
@dict_extractor(("score", "feedback"))
@dict_extractor(("score",))
def _(data: dict[str, JSON], /) -> Graded:
    score = data.get("score")
    feedback = data.get("feedback")
    feedback = feedback.strip() if isinstance(feedback, str) else None

    # Convert relative values
    if isinstance(score, str) and score.strip().endswith("%"):
        score = score.strip().removesuffix("%")
        try:
            score_value = to_decimal(score) / 100
        except ValueError:
            log.warning("Invalid score format: %s", score)
            return Graded(dq.Error(), feedback=feedback)
        else:
            return Graded(score_value, feedback=feedback)

    # Now we extract both the score and the max score, if they are present.
    try:
        score = validate_score(score, out_of_bound=True)
    except ValueError:
        log.warning("Invalid score format: %s", score)
        return Graded(dq.Error(), feedback=feedback)
    else:
        return Graded(score, feedback=feedback)


@lru_cache
def get_valid_keys() -> frozenset[str]:
    keys = iter(FROM_DICT_IMPLEMENTATIONS.keys())
    return frozenset(itertools.chain(*keys))


def _typecheck[T](v: JSON, typ: type[T], /) -> T:
    if isinstance(v, typ):
        return v
    raise ValueError("Unexpected type: {}".format(type(v).__name__))


def _getchecked[T](v: JSON, key: str, typ: type[T], /) -> T:
    if not isinstance(v, dict):
        raise ValueError("Expected a dictionary")
    return _typecheck(v.get(key), typ)
