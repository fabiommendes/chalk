import time
from pathlib import Path

import pytest

from chalk_grader import disqualification as dq
from chalk_grader import models
from chalk_grader.script_grader import ScriptGrader
from chalk_grader.task import Task


def script_grader(tmp_path: Path, body: str, **conf) -> ScriptGrader:
    script = tmp_path / "grade.sh"
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(0o755)
    task = Task("q1", "p1", root=Path(), template=None)
    conf.setdefault("sandbox", "none")
    return ScriptGrader(script, task, models.Autograder(**conf))


class TestScriptLimits:
    def test_timeout_from_conf(self, tmp_path) -> None:
        grader = script_grader(tmp_path, "sleep 10\n", timeout=0.3)
        start = time.time()
        assert grader("s1", "x").score == dq.Timeout()
        assert time.time() - start < 5

    def test_answer_too_large(self, tmp_path) -> None:
        grader = script_grader(
            tmp_path, 'echo 1 > "$CHALK_RESULT"\n', limits={"answer_size": "10B"}
        )
        assert grader("s1", "x" * 11).score == dq.InvalidInput()
        assert grader("s1", "x" * 10).score == 1

    def test_file_size(self, tmp_path) -> None:
        body = 'head -c 100000 /dev/zero > big\nwc -c < big > "$CHALK_RESULT"\n'
        grader = script_grader(tmp_path, body, limits={"file_size": "1KB"})
        graded = grader("s1", "x", keep_files=True)
        assert graded.score <= 1000

    def test_memory(self, tmp_path) -> None:
        body = (
            "python3 -c 'b = bytearray(400_000_000)' && echo 1 > \"$CHALK_RESULT\""
            ' || echo 0 > "$CHALK_RESULT"\n'
        )
        grader = script_grader(tmp_path, body, limits={"memory": "200MB"})
        assert grader("s1", "x").score == 0

    def test_podman_not_implemented(self, tmp_path) -> None:
        grader = script_grader(tmp_path, 'echo 1 > "$CHALK_RESULT"\n', sandbox="podman")
        with pytest.raises(NotImplementedError, match="podman"):
            grader("s1", "x")
