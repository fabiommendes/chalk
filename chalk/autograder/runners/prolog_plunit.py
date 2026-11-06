"""
Test runner of the prolog-plunit profile: runs each plunit test of the
template in a swipl process of its own and writes a JUnit report.

A test that loops, halts or crashes only fails itself. The verdict of a test
is the line `chalk-plunit SECRET pass|fail` that prolog_plunit.pl prints; the
secret is sent on stdin, so the student's output cannot forge it.

It runs inside the sandbox, with the student's program as a child, so it
uses only the standard library and is started with `python -I`.

Usage:

    prolog_plunit.py --swipl SWIPL --answer FILE --report FILE [--timeout SECONDS] PATH...

PATH is a Prolog file of tests or a directory searched for `*.pl` files. The
report has a `testcase` for each test of the PATHs, with `classname` set to
the plunit unit.
"""

import argparse
import os
import secrets
import select
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROLOG = HERE / "prolog_plunit.pl"

#: Longest incomplete line kept while looking for the verdict, in bytes.
MAX_LINE = 64 * 1024


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the plunit tests of the template.")
    parser.add_argument("--swipl", required=True)
    parser.add_argument("--answer", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)

    files = find_files(args.paths)
    suite = ET.Element("testsuite", name="plunit")
    for unit, test in list_tests(args.swipl, files):
        error = run_test(args.swipl, args.answer, unit, test, files, args.timeout)
        case = ET.SubElement(suite, "testcase", classname=unit, name=test)
        if error is not None:
            ET.SubElement(case, "failure", message=error)
        print(f"{unit}:{test}: {error or 'passed'}")
    ET.ElementTree(suite).write(args.report, encoding="unicode")
    return 0


def find_files(paths: list[Path]) -> list[str]:
    files: list[str] = []
    for path in paths:
        if path.is_dir():
            files.extend(str(p) for p in sorted(path.rglob("*.pl")))
        elif path.is_file():
            files.append(str(path))
    return files


def swipl_command(swipl: str, *args: str) -> list[str]:
    return [swipl, "-q", "-f", "none", str(PROLOG), "--", *args]


def list_tests(swipl: str, files: list[str]) -> list[tuple[str, str]]:
    """
    The (unit, test) pairs of the test files, in order.
    """
    try:
        proc = subprocess.run(
            swipl_command(swipl, "list", *files),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return []
    tests: dict[tuple[str, str], None] = {}
    for line in proc.stdout.splitlines():
        unit, tab, test = line.partition("\t")
        if tab and unit and test and "\t" not in test:
            tests[(unit, test)] = None
    return list(tests)


def run_test(
    swipl: str, answer: str, unit: str, test: str, files: list[str], timeout: float
) -> str | None:
    """
    Run one test. Return None when it passed, or why it did not.
    """
    secret = secrets.token_hex(16)
    command = swipl_command(swipl, "test", answer, unit, test, *files)
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as e:
        return f"cannot run swipl: {e.strerror}"
    assert proc.stdin is not None and proc.stdout is not None
    try:
        proc.stdin.write(secret.encode() + b"\n")
        proc.stdin.close()
    except OSError:
        pass

    verdict, timed_out = read_verdict(proc, secret.encode(), timeout)
    if verdict == b"pass":
        return None
    if timed_out:
        return f"timed out after {timeout:g}s"
    if verdict == b"fail":
        return "failed"
    return "the program ended without running the test"


def read_verdict(
    proc: subprocess.Popen[bytes], secret: bytes, timeout: float
) -> tuple[bytes | None, bool]:
    """
    Read the output of the process until it exits or the time runs out, and
    kill its process group. Return the verdict line, if any, and whether the
    time ran out.
    """
    assert proc.stdout is not None
    fd = proc.stdout.fileno()
    prefix = b"chalk-plunit " + secret + b" "
    verdict: bytes | None = None
    pending = b""
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
        *lines, pending = (pending + chunk).split(b"\n")
        pending = pending[-MAX_LINE:]
        for line in lines:
            if line.startswith(prefix):
                verdict = line[len(prefix) :].strip()
        if verdict is not None:
            break
    if pending.startswith(prefix) and verdict is None:
        verdict = pending[len(prefix) :].strip()
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    proc.stdout.close()
    proc.wait()
    return verdict, timed_out and verdict is None


if __name__ == "__main__":
    sys.exit(main())
