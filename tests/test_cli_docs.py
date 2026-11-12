"""
docs/user-manual/cli.md is generated from the CLI. Regenerate it with
`uv run task cli-docs` when a command or option changes.
"""

import os
import subprocess
import sys
from pathlib import Path

DOCS = Path(__file__).parent.parent / "docs" / "user-manual" / "cli.md"


def test_cli_reference_is_up_to_date() -> None:
    cmd = [sys.executable, "-m", "typer", "chalk.cli", "utils", "docs", "--name", "chalk"]
    cmd += ["--title", "Command reference"]
    # The committed reference is rendered by rich; TYPER_USE_RICH=0 (set by r2, for one) changes
    # the escaping of quotes.
    env = {k: v for k, v in os.environ.items() if k not in ("TYPER_USE_RICH", "NO_COLOR")}
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
    assert result.stdout.rstrip() == DOCS.read_text().rstrip(), "run `uv run task cli-docs`"
