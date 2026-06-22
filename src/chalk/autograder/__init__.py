import os
import re
from pathlib import Path

from natsort import natsorted

RUN_AUTOGRADER_SCRIPT_REGEX = re.compile(r"_?autograde")
__all__ = [
    "autograder_scripts",
]


def autograder_scripts(question_root: Path) -> list[Path]:
    """
    Get a list of paths to autograder scripts within the base path.

    Autograder scripts should be located in the autograde.scripts directory within the base path.
    """
    files = {
        p
        for p in question_root.iterdir()
        if p.is_file()
        and RUN_AUTOGRADER_SCRIPT_REGEX.match(p.name)
        and os.access(p, os.X_OK)
    }
    return natsorted(files, key=lambda p: p.name.lower())
