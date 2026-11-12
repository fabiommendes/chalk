"""
Test runner of the stdio profile: runs a program with each `*.in` file on
stdin and records its output. Chalk compares the outputs with the `*.out`
files of the template outside the sandbox, so the expected outputs are never
visible to the student's program.

It runs inside the sandbox, with the student's program as a child, so it
uses only the standard library and is started with `python -I`.

Usage:

    stdio.py --report FILE [--timeout SECONDS] --command CMD PATH...

PATH is a `.in` file or a directory searched for `.in` files. CMD is split
like a shell command line, without running a shell. The report is a JSON
object: {"cases": [{"name": "tests/01", "error": null, "output": "..."}]},
where name is the path of the input without `.in` and error says why the
run failed (timeout, signal, exit code).
"""

import argparse
import json
import os
import select
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

#: Output kept from each run, in bytes. The rest is read and dropped.
MAX_OUTPUT = 64 * 1024

#: Longest text of a line shown in a failure message.
MAX_SHOWN = 80


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a program on each *.in file.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--command", required=True)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)

    command = shlex.split(args.command)
    cases = []
    for case in find_cases(args.paths):
        name = str(case.with_suffix(""))
        output, error = run_case(command, case, args.timeout)
        cases.append({"name": name, "error": error, "output": output})
        print(f"{name}: {error or 'ran'}")
    args.report.write_text(json.dumps({"cases": cases}))
    return 0


def find_cases(paths: list[Path]) -> list[Path]:
    cases: list[Path] = []
    for path in paths:
        if path.is_dir():
            cases.extend(sorted(path.rglob("*.in")))
        elif path.suffix == ".in":
            cases.append(path)
    return cases


def run_case(command: list[str], case: Path, timeout: float) -> tuple[str, str | None]:
    """
    Run the command on one case. Return its output and the reason the run
    failed, or None.
    """
    with case.open("rb") as stdin:
        try:
            proc = subprocess.Popen(
                command, stdin=stdin, stdout=subprocess.PIPE, start_new_session=True
            )
        except OSError as e:
            return "", f"cannot run {shlex.join(command)}: {e.strerror}"
        output, timed_out = read_output(proc, timeout)

    text = output.decode(errors="replace")
    if timed_out:
        return text, f"timed out after {timeout:g}s"
    if proc.returncode < 0:
        return text, f"killed by signal {signal.Signals(-proc.returncode).name}"
    if proc.returncode > 0:
        return text, f"exited with code {proc.returncode}"
    return text, None


def read_output(proc: subprocess.Popen[bytes], timeout: float) -> tuple[bytes, bool]:
    """
    Read the output of the process until it exits or the time runs out, and
    kill its process group.
    """
    assert proc.stdout is not None
    fd = proc.stdout.fileno()
    output = bytearray()
    deadline = time.monotonic() + timeout
    timed_out = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            continue
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        if len(output) < MAX_OUTPUT:
            output += chunk[: MAX_OUTPUT - len(output)]
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    proc.stdout.close()
    proc.wait()
    return bytes(output), timed_out


def compare(output: str, expected: str, mode: str) -> str | None:
    """
    None when the output matches, or a message with the first difference.

    - exact: the same text.
    - lines: the same lines, ignoring spaces at the end of lines and empty
      lines at the end.
    - tokens: the same words, ignoring how they are spaced.
    """
    if mode == "tokens":
        got, want = output.split(), expected.split()
        unit = "word"
    elif mode == "lines":
        got, want = _lines(output), _lines(expected)
        unit = "line"
    elif mode == "exact":
        got, want = output.splitlines(keepends=True), expected.splitlines(keepends=True)
        unit = "line"
    else:
        raise ValueError(f"unknown comparison: {mode!r}")
    if got == want:
        return None

    for i, (a, b) in enumerate(zip(got, want, strict=False), 1):
        if a != b:
            return f"{unit} {i}: expected {_show(b)}, got {_show(a)}"
    if len(got) < len(want):
        return f"output ends before {unit} {len(got) + 1}, expected {_show(want[len(got)])}"
    return f"unexpected {unit} {len(want) + 1}: {_show(got[len(want)])}"


def _lines(text: str) -> list[str]:
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _show(text: str) -> str:
    text = repr(text)
    return text if len(text) <= MAX_SHOWN else text[: MAX_SHOWN - 3] + "..."


if __name__ == "__main__":
    sys.exit(main())
