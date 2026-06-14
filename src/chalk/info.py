import sys
from typing import Any, Literal, cast

from . import conf, roster
from .core import Assignment, iter_assignments
from .data import StructuredFormat, dump_structured_data

InfoFormat = Literal["console"] | StructuredFormat


def get_project_info() -> dict[str, Any]:
    """
    Get global information about the Chalk project, including the roster and assignments.
    """
    cfg = conf.get_classroom()
    students = roster.read_roster()  # noqa: F821
    assignment_data: list[Assignment] = [loader() for id, loader in iter_assignments()]
    return {
        "classroom": cfg.name,
        "teacher": cfg.teacher,
        "lang": cfg.lang,
        "students": len(students),
        "assignments": [assignment.info() for assignment in assignment_data],
    }


def get_debug_info() -> dict[str, Any]:
    """
    Get debug information about the Chalk project, including environment variables and file paths.
    """
    cfg = conf.get_classroom()
    return {
        "classroom": cfg.name,
        "teacher": cfg.teacher,
        "lang": cfg.lang,
        # "chalk_path": conf.get_chalk_path(),
        # "roster_path": conf.get_roster_path(),
        # "assignments_path": conf.get_assignments_path(),
        # "reports_path": conf.get_reports_path(),
    }


def get_version_info() -> dict[str, Any]:
    """
    Get version information about Chalk and key dependencies.
    """
    import chalk

    return {
        "chalk_version": chalk.__version__,
        "python_version": sys.version,
    }


def display_project_info(format: InfoFormat = "console") -> None:
    """
    Rich print the result of get_project_info().
    """
    info = get_project_info()

    match format:
        case "json":
            dump_structured_data(info, format="json")
            return
        case "yaml":
            dump_structured_data(info, format="yaml")
            return
        case "console":
            pass
        case _:
            raise ValueError(f"Unsupported format: {format}")

    # FIXME: pretty console print
    dump_structured_data(info)


def display_debug_info(format: InfoFormat = "console") -> None:
    """
    Rich print the result of get_debug_info().
    """
    info = get_debug_info()

    match format:
        case "json":
            dump_structured_data(info, format="json")
            return
        case "yaml":
            dump_structured_data(info, format="yaml")
            return
        case "console":
            pass
        case _:
            raise ValueError(f"Unsupported format: {format}")

    # FIXME: pretty console print
    dump_structured_data(info)


def display_version_info(format: InfoFormat = "console") -> None:
    """
    Rich print the result of get_version_info().
    """
    info = get_version_info()

    match format:
        case "json":
            dump_structured_data(info, format="json")
            return
        case "yaml":
            dump_structured_data(info, format="yaml")
            return
        case "console":
            pass
        case _:
            raise ValueError(f"Unsupported format: {format}")

    # FIXME: pretty console print
    dump_structured_data(info)


def validate_info_format(format: str) -> InfoFormat:
    """
    Validate the format for printing global information.
    """
    if format not in {"json", "yaml", "console"}:
        raise ValueError("Invalid format. Must be one of: json, yaml, console.")
    return cast(InfoFormat, format)
