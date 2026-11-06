"""
Scoring modes of the profiles that produce per-test results.

A scorer receives the outcome of every expected test (a missing test counts
as failed) and the names of the expected tests, and returns the score. The
proportional mode (passed / expected) has no scorer: it is the default of
the report readers.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..core import models

__all__ = ["SCRIPT_TIMEOUT", "ScoringError", "ScriptScorer", "all_or_nothing", "make_scorer"]

#: Seconds a scoring script has to print the score.
SCRIPT_TIMEOUT = 10.0

#: Longest stderr of a scoring script kept in the error message, in characters.
MAX_STDERR = 2000

_FRACTION = re.compile(r"(\d+)/(\d+)")
_DECIMAL = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)")

#: Tests as {"name", "passed", "message"} and the names of the expected tests.
type Scorer = Callable[[list[dict[str, Any]], list[str]], Fraction]


class ScoringError(RuntimeError):
    """
    The scoring script failed or printed something that is not a score. It is
    an infrastructure error, not a grade.
    """


def all_or_nothing(tests: list[dict[str, Any]], expected: list[str]) -> Fraction:
    """
    1 when every expected test passed, else 0.
    """
    return Fraction(int(all(t["passed"] for t in tests)))


class ScriptScorer:
    """
    Scores with a teacher script, run outside the sandbox with the current
    Python in isolated mode.

    The script reads `{"tests": [...], "expected": [...]}` from stdin and
    prints the score, a decimal or `n/d`, in [0, 1].
    """

    def __init__(self, path: Path, timeout: float | None = None) -> None:
        self.path = path
        self.timeout = SCRIPT_TIMEOUT if timeout is None else timeout

    def __call__(self, tests: list[dict[str, Any]], expected: list[str]) -> Fraction:
        if not self.path.is_file():
            raise ScoringError(f"scoring script not found: {self.path}")
        payload = json.dumps({"tests": tests, "expected": expected})
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(self.path)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.path.parent,
            )
        except subprocess.TimeoutExpired:
            raise ScoringError(
                f"scoring script {self.path.name} timed out after {self.timeout:g}s"
            ) from None
        if proc.returncode != 0:
            stderr = proc.stderr.strip()[-MAX_STDERR:]
            raise ScoringError(
                f"scoring script {self.path.name} exited with code {proc.returncode}:\n{stderr}"
            )
        return self._parse(proc.stdout)

    def _parse(self, out: str) -> Fraction:
        text = out.strip()
        if m := _FRACTION.fullmatch(text):
            if int(m[2]) == 0:
                raise ScoringError(f"scoring script {self.path.name} printed a zero denominator")
            value = Fraction(int(m[1]), int(m[2]))
        elif _DECIMAL.fullmatch(text):
            value = Fraction(Decimal(text))
        else:
            raise ScoringError(
                f"scoring script {self.path.name} printed something that is not a score: {text[:100]!r}"
            )
        if not 0 <= value <= 1:
            raise ScoringError(
                f"scoring script {self.path.name} printed a score out of [0, 1]: {text}"
            )
        return value


def make_scorer(conf: models.Autograder, root: Path) -> Scorer | None:
    """
    The scorer of the configuration, None for the proportional mode. The
    script path is relative to root, the folder of the configuration.
    """
    match conf.scoring:
        case "all-or-nothing":
            return all_or_nothing
        case "script":
            assert conf.scoring_script is not None
            return ScriptScorer(root / conf.scoring_script)
        case _:
            return None
