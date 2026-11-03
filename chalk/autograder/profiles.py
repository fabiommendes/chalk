"""
Parts of the profiles that run the template tests: replacing the student's copies of trusted files and scoring a
JUnit report against the tests collected in the prepare step.
"""

from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from fractions import Fraction
from logging import getLogger
from pathlib import Path

from ..core import disqualification as dq
from ..core.grader import Graded
from .result_extractor import MAX_RESULT_SIZE

__all__ = [
    "PrepareError",
    "check_relative",
    "install_trusted_files",
    "read_report",
    "read_stdio_report",
    "score_report",
    "stdio_keys",
]

log = getLogger(__name__)

#: Longest failure message of a test shown in the feedback.
MAX_MESSAGE = 200

#: Test key in a JUnit report: (classname, name).
type TestKey = tuple[str, str]


class PrepareError(RuntimeError):
    """
    The template cannot be prepared: missing lock file, failed probe or
    dependency install, or a reference run without tests.
    """


def check_relative(name: str) -> None:
    """
    Reject a path that is not inside the directory it is relative to, or
    that a command could read as an option.
    """
    if name.startswith("-") or Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError(f"path must be relative and inside the directory: {name}")


def install_trusted_files(
    root: Path, template: Path, names: Iterable[str]
) -> list[tuple[Path, Path]]:
    """
    Replace the files and directories with the given names in root by the
    template's, or remove them when the template does not have them.

    Return the (source, target) pairs to mount read only over the working
    directory: the copies themselves, so files removed from them later stay
    removed.
    """
    overlays: list[tuple[Path, Path]] = []
    for name in names:
        check_relative(name)
        source = template / name
        target = root / name
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()

        if source.is_dir():
            shutil.copytree(source, target, symlinks=False)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        else:
            continue
        overlays.append((target, target))
    return overlays


def read_report(path: Path, expected: Mapping[TestKey, str], extra: Sequence[str] = ()) -> Graded:
    if path.stat().st_size > MAX_RESULT_SIZE:
        return Graded(dq.Error(), feedback="Test report is too large.")
    return score_report(path.read_text(errors="replace"), expected, extra)


def score_report(src: str, expected: Mapping[TestKey, str], extra: Sequence[str] = ()) -> Graded:
    """
    Score a JUnit report against the expected tests, a map from the
    (classname, name) pair in the report to the name shown in the feedback.

    A test passes when it is in the report without failure, error or skip.
    Missing tests, tests skipped by the student's code and repeated entries
    with a failure count as failures. Tests not in the expected list are
    ignored. The JUnit reports of the services in extra count as part of the
    report.
    """
    try:
        results, errors = junit_results(src)
    except ET.ParseError as e:
        return Graded(dq.Error(), feedback=f"Invalid JUnit report: {e}")
    return _score(expected, results, errors, extra)


def junit_results(src: str) -> tuple[dict[TestKey, str | None], list[str]]:
    """
    Outcome of each test in a JUnit report, None when it passed or the
    failure message, and the collection errors (entries without class name).

    Raises ET.ParseError for an invalid report.
    """
    root = ET.fromstring(src)
    results: dict[TestKey, str | None] = {}
    errors: list[str] = []
    for case in root.iter("testcase"):
        key = (case.get("classname") or "", case.get("name") or "")
        problems = [
            p for tag in ("failure", "error", "skipped") if (p := case.find(tag)) is not None
        ]
        if problems and results.get(key) is None:
            results[key] = _message(problems[0])
        else:
            results.setdefault(key, None)
        if not key[0] and (error := case.find("error")) is not None:
            errors.append(f"- {key[1]}: {error.get('message') or 'error'}")
    return results, errors


def read_stdio_report(
    path: Path,
    expected: Mapping[TestKey, str],
    template: Path,
    mode: str,
    extra: Sequence[str] = (),
) -> Graded:
    """
    Score the report of chalk's stdio runner: each case passes when it ran
    without error and its output matches the template's `.out` file. The
    JUnit reports of the services in extra count as part of the report.
    """
    from .runners.stdio import compare

    if path.stat().st_size > MAX_RESULT_SIZE:
        return Graded(dq.Error(), feedback="Test report is too large.")
    try:
        cases = {c["name"]: c for c in json.loads(path.read_text(errors="replace"))["cases"]}
    except (ValueError, KeyError, TypeError) as e:
        return Graded(dq.Error(), feedback=f"Invalid stdio report: {e}")

    results: dict[TestKey, str | None] = {}
    for key in expected:
        if key[0] != "stdio":
            continue
        case = cases.get(key[1])
        if not isinstance(case, dict):
            continue
        elif case.get("error"):
            results[key] = str(case["error"]) or "error"
        else:
            want = (template / f"{key[1]}.out").read_text(errors="replace")
            results[key] = compare(str(case.get("output") or ""), want, mode)
    return _score(expected, results, [], extra)


def stdio_keys(src: str) -> list[TestKey]:
    """
    The tests in a report of the stdio runner.
    """
    try:
        return [("stdio", str(c["name"])) for c in json.loads(src)["cases"]]
    except (ValueError, KeyError, TypeError):
        return []


def _score(
    expected: Mapping[TestKey, str],
    results: dict[TestKey, str | None],
    errors: list[str],
    extra: Sequence[str],
) -> Graded:
    for src in extra:
        try:
            more, _ = junit_results(src)
        except ET.ParseError as e:
            errors.append(f"- invalid service report: {e}")
            continue
        for key, message in more.items():
            if results.get(key) is None:
                results[key] = message

    unknown = [k for k in results if k not in expected and k[0]]
    if unknown:
        log.warning(f"Report has {len(unknown)} tests that are not in the template: {unknown[:5]}")

    failures = {
        k: "(not run)" if k not in results else results[k] or ""
        for k in expected
        if results.get(k, "") is not None
    }
    return _graded(expected, failures, errors)


def _graded(
    expected: Mapping[TestKey, str], failures: Mapping[TestKey, str], errors: list[str]
) -> Graded:
    lines: list[str] = []
    if failures:
        lines += ["Failed tests:"]
        lines += [
            f"- {expected[k]}" + (f" {m}" if m == "(not run)" else f": {m}" if m else "")
            for k, m in failures.items()
        ]
    if errors:
        lines += ["Errors:", *errors]
    passed = len(expected) - len(failures)
    return Graded(Fraction(passed, len(expected)), feedback="\n".join(lines) or None)


def _message(element: ET.Element) -> str:
    """
    First lines of a failure message, on one line.
    """
    text = element.get("message") or element.text or ""
    text = " ".join(text.split())
    return text if len(text) <= MAX_MESSAGE else text[: MAX_MESSAGE - 3] + "..."
