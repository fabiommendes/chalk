#!/usr/bin/env python3
"""Record `r2:` markers while reading the code, then write them all at once.

A marker is a comment that ties a piece of code to the documents about it:

    # r2: adr-0003, issue/retry-on-timeout

Writing markers one by one shifts the lines of the next ones in the same file.
This script records each marker against the line and its text as they are
now, in `.r2/markers.json`, and `apply` writes every marker of a file in one
pass, bottom up, finding each target again by its text if the file changed.

    markers.py add PATH LINE REF... record a marker above PATH:LINE
    markers.py list [--json]        the recorded markers, numbered
    markers.py drop N...            forget markers by number
    markers.py apply [--dry-run]    write them into the code

A REF is `adr-NNNN`, `issue/<slug>`, `rfc/<slug>` or `spec/<slug>`, and must
name an existing document under `dev/`. `adr/NNNN` is read as `adr-NNNN`.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

REF = re.compile(r"^(adr-\d{4}|(issue|rfc|spec)/[a-z0-9][a-z0-9-]*)$")
ADR_SLASH = re.compile(r"^adr/(\d{4})$")
FOLDERS = {
    "adr": "dev/adr",
    "issue": "dev/issues",
    "rfc": "dev/rfc",
    "spec": "dev/spec",
}

# Comment opener and closer by file suffix or name.
HASH = ("#", "")
SLASH = ("//", "")
DASH = ("--", "")
SEMI = (";", "")
HTML = ("<!--", " -->")
BLOCK = ("/*", " */")
COMMENTS: dict[str, tuple[str, str]] = {
    **dict.fromkeys(
        [
            ".py",
            ".pyi",
            ".sh",
            ".bash",
            ".zsh",
            ".fish",
            ".rb",
            ".pl",
            ".r",
            ".toml",
            ".yaml",
            ".yml",
            ".ex",
            ".exs",
            ".nix",
            ".cmake",
            ".ps1",
            ".tf",
            ".jl",
            ".cr",
            ".nim",
            ".coffee",
        ],
        HASH,
    ),
    **dict.fromkeys(["makefile", "dockerfile", "justfile", "containerfile"], HASH),
    **dict.fromkeys(
        [
            ".js",
            ".mjs",
            ".cjs",
            ".ts",
            ".mts",
            ".cts",
            ".jsx",
            ".tsx",
            ".rs",
            ".go",
            ".java",
            ".c",
            ".h",
            ".cc",
            ".cpp",
            ".hpp",
            ".cs",
            ".kt",
            ".kts",
            ".swift",
            ".scala",
            ".dart",
            ".php",
            ".zig",
            ".proto",
            ".gleam",
            ".v",
            ".groovy",
        ],
        SLASH,
    ),
    **dict.fromkeys([".sql", ".lua", ".hs", ".elm", ".ada", ".vhd"], DASH),
    **dict.fromkeys(
        [".lisp", ".clj", ".cljs", ".el", ".scm", ".rkt", ".asm", ".ini"], SEMI
    ),
    **dict.fromkeys(
        [".html", ".htm", ".xml", ".svg", ".md", ".vue", ".svelte", ".astro"], HTML
    ),
    **dict.fromkeys([".css", ".scss", ".less"], BLOCK),
}
EXISTING = re.compile(
    r"^(?P<indent>\s*)(#|//|--|;|<!--|/\*|\*)\s*r2:\s+(?P<refs>.*?)\s*(-->|\*/)?\s*$"
)


@dataclass
class Marker:
    path: str
    line: int
    anchor: str
    refs: list[str] = field(default_factory=list)


def root() -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(out.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd()


def store(base: Path) -> Path:
    return base / ".r2" / "markers.json"


def load(base: Path) -> list[Marker]:
    file = store(base)
    if not file.exists():
        return []
    return [Marker(**item) for item in json.loads(file.read_text())]


def save(base: Path, markers: list[Marker]) -> None:
    file = store(base)
    file.parent.mkdir(exist_ok=True)
    data = [asdict(m) for m in markers]
    file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def comment_for(path: Path) -> tuple[str, str] | None:
    return COMMENTS.get(path.suffix.lower()) or COMMENTS.get(path.name.lower())


def normalize(ref: str) -> str:
    """The written form of REF: `adr/NNNN` becomes `adr-NNNN`."""
    return ADR_SLASH.sub(r"adr-\1", ref)


def check_ref(base: Path, ref: str) -> str | None:
    """Return an error message, or None when REF names an existing document."""
    if not REF.match(ref):
        return f"{ref!r} is not adr-NNNN, issue/<slug>, rfc/<slug> or spec/<slug>"
    kind, name = re.split(r"[/-]", ref, maxsplit=1)
    folder = base / FOLDERS[kind]
    pattern = f"{name}-*.md" if kind == "adr" else f"{name}.md"
    if not any(folder.glob(pattern)):
        return f"{ref!r} cites no file in {FOLDERS[kind]}/"
    return None


def merge(old: list[str], new: list[str]) -> list[str]:
    return old + [r for r in new if r not in old]


def add(base: Path, path: str, line: int, refs: list[str]) -> int:
    refs = [normalize(r) for r in refs]
    errors = [e for r in refs if (e := check_ref(base, r))]
    file = Path(path).resolve()
    if not file.is_file():
        errors.append(f"{path} is not a file")
    elif comment_for(file) is None:
        errors.append(f"{path}: no comment syntax known for this file type")
    if errors:
        print("\n".join(f"error: {e}" for e in errors), file=sys.stderr)
        return 1
    lines = file.read_text().splitlines()
    if not 1 <= line <= len(lines):
        print(f"error: {path} has {len(lines)} lines", file=sys.stderr)
        return 1
    if not lines[line - 1].strip():
        print(f"error: {path}:{line} is blank; point at the code", file=sys.stderr)
        return 1
    rel = file.relative_to(base).as_posix()
    markers = load(base)
    for m in markers:
        if m.path == rel and m.line == line:
            m.refs = merge(m.refs, refs)
            break
    else:
        markers.append(Marker(rel, line, lines[line - 1].strip(), refs))
    save(base, markers)
    print(f"recorded {rel}:{line}  r2: {', '.join(refs)}")
    return 0


def show(base: Path, as_json: bool) -> int:
    markers = load(base)
    if as_json:
        print(json.dumps([asdict(m) for m in markers], indent=2, ensure_ascii=False))
        return 0
    for n, m in enumerate(markers, 1):
        anchor = m.anchor if len(m.anchor) <= 60 else m.anchor[:57] + "..."
        print(f"{n:>3}  {m.path}:{m.line}  r2: {', '.join(m.refs)}  | {anchor}")
    return 0


def drop(base: Path, numbers: list[int]) -> int:
    markers = load(base)
    keep = [m for n, m in enumerate(markers, 1) if n not in set(numbers)]
    save(base, keep)
    print(f"dropped {len(markers) - len(keep)}, {len(keep)} left")
    return 0


def locate(lines: list[str], m: Marker) -> int | None:
    """Index of the marker's target line, by its text, nearest the recorded line."""
    i = m.line - 1
    if i < len(lines) and lines[i].strip() == m.anchor:
        return i
    hits = [j for j, text in enumerate(lines) if text.strip() == m.anchor]
    return min(hits, key=lambda j: abs(j - i)) if hits else None


def insertion(lines: list[str], target: int, python: bool) -> int:
    """Where the marker goes: above the target and above its decorators."""
    at = target
    while python and at > 0 and lines[at - 1].lstrip().startswith("@"):
        at -= 1
    return at


def apply_file(base: Path, rel: str, markers: list[Marker], dry: bool) -> list[Marker]:
    """Write the markers of one file. Return the ones that could not be placed."""
    file = base / rel
    opener, closer = comment_for(file) or HASH
    text = file.read_text()
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    python = file.suffix in (".py", ".pyi")

    # Group by insertion point, so two markers for one place become one line.
    places: dict[int, list[str]] = {}
    failed: list[Marker] = []
    indents: dict[int, str] = {}
    for m in markers:
        target = locate(lines, m)
        if target is None:
            failed.append(m)
            print(f"not found: {m.path}:{m.line}  | {m.anchor}", file=sys.stderr)
            continue
        at = insertion(lines, target, python)
        places[at] = merge(places.get(at, []), m.refs)
        target_line = lines[target]
        indents[at] = target_line[: len(target_line) - len(target_line.lstrip())]

    # Bottom up: an insertion never shifts the places still to write.
    for at in sorted(places, reverse=True):
        above = EXISTING.match(lines[at - 1]) if at > 0 else None
        if above:
            found = re.split(r"[,\s]+", above["refs"])
            refs = [normalize(r.strip()) for r in found if r.strip()]
            refs = merge(refs, places[at])
            line = f"{above['indent']}{opener} r2: {', '.join(refs)}{closer}"
            print(f"{rel}  {line.strip()}  (merged)  | {lines[at].strip()}")
            lines[at - 1] = line
        else:
            line = f"{indents[at]}{opener} r2: {', '.join(places[at])}{closer}"
            print(f"{rel}  {line.strip()}  | {lines[at].strip()}")
            lines.insert(at, line)

    if not dry:
        end = newline if text.endswith(("\n", "\r\n")) else ""
        file.write_text(newline.join(lines) + end)
    return failed


def apply(base: Path, dry: bool) -> int:
    markers = load(base)
    by_file: dict[str, list[Marker]] = {}
    for m in markers:
        by_file.setdefault(m.path, []).append(m)
    failed: list[Marker] = []
    for rel, group in by_file.items():
        if not (base / rel).is_file():
            print(f"missing file: {rel}", file=sys.stderr)
            failed += group
            continue
        failed += apply_file(base, rel, group, dry)
    if not dry:
        save(base, failed)
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("add", help="record a marker above PATH:LINE")
    p.add_argument("path")
    p.add_argument("line", type=int)
    p.add_argument("refs", nargs="+")
    p = sub.add_parser("list", help="the recorded markers, numbered")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("drop", help="forget markers by number")
    p.add_argument("numbers", nargs="+", type=int)
    p = sub.add_parser("apply", help="write the markers into the code")
    p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base = root()
    if args.command == "add":
        return add(base, args.path, args.line, args.refs)
    if args.command == "list":
        return show(base, args.json)
    if args.command == "drop":
        return drop(base, args.numbers)
    return apply(base, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
