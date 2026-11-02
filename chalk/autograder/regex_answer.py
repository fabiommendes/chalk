"""
Grade answers that are regular expressions (the `regex` autograder profile).

The student's regex runs in a separate Python process, because a regex with
catastrophic backtracking cannot be interrupted inside the process that runs
it. Each example has its own timeout; when it expires, the worker is killed,
the example counts as wrong and a new worker takes the remaining examples.
"""

from __future__ import annotations

import json
import selectors
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from ..core import StudentId, models
from ..core import disqualification as dq
from ..core.grader import Graded, Grader

#: Seconds each example may take.
EXAMPLE_TIMEOUT = 1.0

#: Address space of the worker process.
WORKER_MEMORY = 512 * 1024 * 1024

WORKER = """
import json, re, resource, sys
resource.setrlimit(resource.RLIMIT_AS, (int(sys.argv[3]), int(sys.argv[3])))
try:
    pattern = re.compile(sys.argv[1])
except re.error as e:
    print(json.dumps({"error": str(e)}), flush=True)
    raise SystemExit
print(json.dumps({"ok": True}), flush=True)
match = pattern.fullmatch if sys.argv[2] == "full" else pattern.search
for line in sys.stdin:
    print(json.dumps(match(json.loads(line)) is not None), flush=True)
"""


class InvalidRegex(Exception):
    pass


@dataclass(frozen=True)
class RegexAnswerGrader(Grader[Any]):
    """
    Grade a regex answer by the examples it must match and must not match.

    The score is the fraction of examples with the expected outcome.
    """

    conf: models.Autograder
    example_timeout: float = EXAMPLE_TIMEOUT

    def __post_init__(self) -> None:
        if not self.conf.match and not self.conf.reject:
            raise ValueError("the regex profile needs examples in `match` or `reject`")

    def __call__(self, id: StudentId, answer: Any, /, **kwargs: Any) -> Graded | None:
        if not isinstance(answer, str):
            return Graded(dq.InvalidInput(), feedback="The answer must be a regex.")
        if len(answer.encode()) > self.conf.limits.answer_size:
            limit = self.conf.limits.answer_size
            return Graded(dq.InvalidInput(), feedback=f"The answer is larger than {limit} bytes.")

        pattern = answer.rstrip("\r\n")
        if not pattern:
            return Graded(Fraction(0), feedback="Empty regex.")

        examples = [(ex, True) for ex in self.conf.match] + [(ex, False) for ex in self.conf.reject]
        try:
            outcomes = run_examples(
                pattern, [ex for ex, _ in examples], self.conf.regex_mode, self.example_timeout
            )
        except InvalidRegex as e:
            return Graded(Fraction(0), feedback=f"Invalid regex: {e}")

        wrong: list[str] = []
        for (example, expected), outcome in zip(examples, outcomes, strict=True):
            if outcome is None:
                wrong.append(f"- took too long on {example!r}")
            elif outcome != expected:
                verb = "should match" if expected else "should not match"
                wrong.append(f"- {verb} {example!r}")

        score = Fraction(len(examples) - len(wrong), len(examples))
        return Graded(score, feedback="\n".join(wrong) or None)


def run_examples(pattern: str, examples: list[str], mode: str, timeout: float) -> list[bool | None]:
    """
    Test the pattern against each example in a worker process.

    Returns True or False for each example, or None when the example timed
    out. Raises InvalidRegex if the pattern does not compile.
    """
    outcomes: list[bool | None] = []
    pending = list(examples)
    while pending:
        with _Worker(pattern, mode) as worker:
            worker.check_compiled(timeout)
            while pending:
                outcome = worker.test(pending[0], timeout)
                pending.pop(0)
                outcomes.append(outcome)
                if outcome is None:
                    break  # the worker was killed; start another one
    return outcomes


class _Worker:
    def __init__(self, pattern: str, mode: str) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-c", WORKER, pattern, mode, str(WORKER_MEMORY)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env={},
        )
        assert self.process.stdout is not None
        self._selector = selectors.DefaultSelector()
        self._selector.register(self.process.stdout, selectors.EVENT_READ)

    def __enter__(self) -> _Worker:
        return self

    def __exit__(self, *exc: object) -> None:
        self.process.kill()
        self.process.wait()
        self._selector.close()

    def _read(self, timeout: float) -> Any:
        if not self._selector.select(timeout):
            return None
        assert self.process.stdout is not None
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("regex worker died")
        return json.loads(line)

    def check_compiled(self, timeout: float) -> None:
        try:
            reply = self._read(timeout)
        except RuntimeError:
            raise InvalidRegex("the regex uses too much memory") from None
        if reply is None:
            raise InvalidRegex("the regex took too long to compile")
        if "error" in reply:
            raise InvalidRegex(reply["error"])

    def test(self, example: str, timeout: float) -> bool | None:
        assert self.process.stdin is not None
        try:
            self.process.stdin.write(json.dumps(example) + "\n")
            self.process.stdin.flush()
        except BrokenPipeError:
            return None
        try:
            return self._read(timeout)
        except RuntimeError:
            return None  # killed by the memory limit
