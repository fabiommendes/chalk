import json
from pathlib import Path
from typing import NamedTuple

from ..core import Grade
from ..protocols import JSON
from ..types import Answer

__all__ = [
    "GradeAndFeedback",
    "extract_result",
    "render_answer",
]


class GradeAndFeedback(NamedTuple):
    grade: Grade | None
    feedback: str | None


def extract_result(report_path: Path) -> GradeAndFeedback:
    """
    Extract the answer from the given report file and update the response accordingly.

    This is a placeholder implementation. The actual extraction logic will depend on the format of the report file and how the answer is represented within it.
    """
    src = report_path.read_text()
    try:
        data = json.loads(src)
        return _extract_result_from_structured_data(data)
    except json.JSONDecodeError:
        pass

    raise NotImplementedError("Report file format not supported for answer extraction.")


def _extract_result_from_structured_data(data: JSON) -> GradeAndFeedback:
    """
    Extract the answer from the given data dictionary and update the response accordingly.

    This is a placeholder implementation. The actual extraction logic will depend on the structure of the data and how the answer is represented within it.
    """
    if data is None:
        return GradeAndFeedback(None, None)
    if isinstance(data, (int, float)):
        return GradeAndFeedback(Grade(data), None)
    if isinstance(data, dict) and "grade" in data:
        return GradeAndFeedback(Grade(data["grade"]), data.get("answer"))

    if isinstance(data, list):
        keys: set[str] = set()
        for item in data:
            if isinstance(item, dict):
                keys.update(item.keys())

        # Pytest JSON reports have a "outcome" field that can be "passed", "failed", or "skipped"
        if "outcome" in keys:
            return _extract_result_from_pytest_report(data)

    raise NotImplementedError("Data format not supported for answer extraction.")


def _extract_result_from_pytest_report(
    data: list[dict[str, JSON]],
) -> GradeAndFeedback:
    """
    Extract the answer from a pytest JSON report.

    This is a placeholder implementation. The actual extraction logic will depend on the structure of the pytest report and how the grade and feedback are represented within it.
    """
    total = 0
    passed = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        outcome = item.get("outcome")
        if outcome == "passed":
            passed += 1
        total += 1

    grade = Grade(passed / total) if total > 0 else None
    return GradeAndFeedback(grade, "Passed: {}/{}".format(passed, total))


def render_answer(answer: Answer) -> str:
    if isinstance(answer, str):
        return answer
    elif isinstance(answer, bytes):
        return answer.decode()
    else:
        raise ValueError("Unsupported answer type: {}".format(type(answer)))
