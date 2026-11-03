"""
Parts shared by the profiles that run the template tests (python-pytest,
rust-cargo): replacing the student's copies of trusted files and scoring a
JUnit report against the tests collected in the prepare step.
"""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from fractions import Fraction
from logging import getLogger
from pathlib import Path

from ..core import disqualification as dq
from ..core.grader import Graded
from .result_extractor import MAX_RESULT_SIZE

__all__ = ["PrepareError", "install_trusted_files", "read_report", "score_report"]

log = getLogger(__name__)

#: Test key in a JUnit report: (classname, name).
type TestKey = tuple[str, str]


class PrepareError(RuntimeError):
    """
    The template cannot be prepared: missing lock file, failed dependency
    install, failed build or failed test collection.
    """


def install_trusted_files(
    root: Path, template: Path, names: Iterable[str]
) -> list[tuple[Path, Path]]:
    """
    Replace the files and directories with the given names in root by the
    template's, or remove them when the template does not have them.

    Return the (source, target) pairs to mount read only over the working
    directory.
    """
    overlays: list[tuple[Path, Path]] = []
    for name in names:
        if name.startswith("-") or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError(f"test path must be relative to the template: {name}")
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
        overlays.append((source, target))
    return overlays


def read_report(path: Path, expected: Mapping[TestKey, str]) -> Graded:
    if path.stat().st_size > MAX_RESULT_SIZE:
        return Graded(dq.Error(), feedback="Test report is too large.")
    return score_report(path.read_text(errors="replace"), expected)


def score_report(src: str, expected: Mapping[TestKey, str]) -> Graded:
    """
    Score a JUnit report against the expected tests, a map from the
    (classname, name) pair in the report to the name shown in the feedback.

    A test passes when it is in the report without failure, error or skip.
    Missing tests, tests skipped by the student's code and repeated entries
    with a failure count as failures. Tests not in the expected list are
    ignored.
    """
    try:
        root = ET.fromstring(src)
    except ET.ParseError as e:
        return Graded(dq.Error(), feedback=f"Invalid JUnit report: {e}")

    outcomes: dict[TestKey, bool] = {}
    errors: list[str] = []
    for case in root.iter("testcase"):
        key = (case.get("classname") or "", case.get("name") or "")
        ok = all(case.find(tag) is None for tag in ("failure", "error", "skipped"))
        outcomes[key] = outcomes.get(key, True) and ok
        if not key[0] and (error := case.find("error")) is not None:
            errors.append(f"- {key[1]}: {error.get('message') or 'error'}")

    unknown = [k for k in outcomes if k not in expected and k[0]]
    if unknown:
        log.warning(f"Report has {len(unknown)} tests that are not in the template: {unknown[:5]}")

    failed = [(k, n) for k, n in expected.items() if outcomes.get(k) is not True]
    passed = len(expected) - len(failed)
    lines: list[str] = []
    if failed:
        lines += ["Failed tests:"]
        lines += [f"- {n}" + ("" if k in outcomes else " (not run)") for k, n in failed]
    if errors:
        lines += ["Errors:", *errors]
    return Graded(Fraction(passed, len(expected)), feedback="\n".join(lines) or None)
