"""
docs/user-manual/cli.md is generated from the CLI. Regenerate it with
`uv run task cli-docs` when a command or option changes.
"""

import subprocess
import sys
from pathlib import Path

DOCS = Path(__file__).parent.parent / "docs" / "user-manual" / "cli.md"


def test_cli_reference_is_up_to_date() -> None:
    cmd = [sys.executable, "-m", "typer", "chalk.cli", "utils", "docs", "--name", "chalk"]
    cmd += ["--title", "Command reference"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert result.stdout.rstrip() == DOCS.read_text().rstrip(), "run `uv run task cli-docs`"
