import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal, cast

from .core import Classroom, Quiz
from .data import StructuredFormat, dump_structured_data

InfoFormat = Literal["console"] | StructuredFormat

DEPENDENCIES = ("mdq", "typer", "pydantic", "pandas", "rich")


def get_project_info() -> dict[str, Any]:
    """
    Get global information about the Chalk project, including the roster and quizzes.
    """
    cfg = Classroom.load()
    students = cfg.get_roster()
    quiz_data: list[Quiz] = [quiz for quiz in cfg.iter_quizzes()]
    return {
        "classroom": cfg.name,
        "teacher": cfg.teacher,
        "lang": cfg.lang,
        "students": len(students),
        "quizzes": [quiz.info() for quiz in quiz_data],
    }


def get_debug_info() -> dict[str, Any]:
    """
    The versions, plus the paths of the classroom and the chalk environment
    variables. Secrets show only whether they are set.
    """
    from .core.classroom import find_project_root

    root = find_project_root()
    env = {
        name: ("<set>" if "KEY" in name or "TOKEN" in name else value)
        for name, value in sorted(os.environ.items())
        if name.startswith(("CHALK_", "CODEHOOD_"))
    }
    return {
        **get_version_info(),
        "root": str(root) if root else None,
        "cwd": str(Path.cwd()),
        "env": env,
    }


def get_version_info() -> dict[str, Any]:
    """
    The versions of chalk, Python and the main dependencies.
    """
    import chalk

    deps = {}
    for name in DEPENDENCIES:
        try:
            deps[name] = version(name)
        except PackageNotFoundError:
            deps[name] = None
    return {"chalk": chalk.__version__, "python": sys.version.split()[0], **deps}


def display_debug_info(format: InfoFormat = "console") -> None:
    dump_structured_data(get_debug_info(), format=None if format == "console" else format)


def display_version_info(format: InfoFormat = "console") -> None:
    dump_structured_data(get_version_info(), format=None if format == "console" else format)


def validate_info_format(format: str) -> InfoFormat:
    """
    Validate the format for printing global information.
    """
    if format not in {"json", "yaml", "console"}:
        raise ValueError("Invalid format. Must be one of: json, yaml, console.")
    return cast(InfoFormat, format)
