"""
Signs of tampering in a submission: code that refers to the report of the
autograder or uses the tricks that forge it from inside the test process.

A match is not proof: the result is a note for the teacher, and the score is
not changed. Code obfuscated on purpose is not found.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

__all__ = ["COMMON", "scan"]

#: Patterns searched in every text file of the submission.
COMMON = {
    "refers to the report file": r"CHALK_RESULT",
    "refers to JUnit reports": r"(?i)junit",
    "reads /proc": r"/proc/",
}

#: Files larger than this are not read.
MAX_FILE_SIZE = 1_000_000

#: Matches listed in the notes; the rest are counted.
MAX_MATCHES = 20

_SKIP_DIRS = {".git", "__pycache__", "node_modules", "target", "elm-stuff", ".venv"}


def scan(
    root: Path,
    *,
    template: Path | None,
    patterns: Mapping[str, Mapping[str, str]],
    skip: Iterable[str] = (),
) -> list[str]:
    """
    Lines like "calc.py:3: refers to the report file" for the files of root
    that match a pattern.

    Args:
        root: the student's working directory.
        template: files with the same content as the template's are skipped.
        patterns: glob -> {reason: regex}, besides COMMON for every file.
        skip: files and directories of root that are not the student's, such
            as the template tests.
    """
    compiled = [
        (glob, [(reason, re.compile(regex)) for reason, regex in table.items()])
        for glob, table in [("**/*", COMMON), *patterns.items()]
    ]
    skipped = {root / name for name in skip}
    found: list[str] = []
    for path in sorted(_files(root, skipped)):
        rel = path.relative_to(root)
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if template is not None and _same(template / rel, text):
            continue
        for glob, table in compiled:
            if not rel.full_match(glob):
                continue
            for reason, regex in table:
                if match := regex.search(text):
                    line = text.count("\n", 0, match.start()) + 1
                    found.append(f"{rel}:{line}: {reason}")
    if len(found) > MAX_MATCHES:
        found = [*found[:MAX_MATCHES], f"... and {len(found) - MAX_MATCHES} more"]
    return found


def _files(root: Path, skipped: set[Path]) -> Iterable[Path]:
    for base, dirs, files in root.walk():
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and base / d not in skipped]
        for name in files:
            path = base / name
            if path in skipped or name.startswith("chalk."):
                continue
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_FILE_SIZE:
                yield path


def _same(path: Path, text: str) -> bool:
    try:
        return path.is_file() and path.read_text() == text
    except (OSError, UnicodeDecodeError):
        return False
