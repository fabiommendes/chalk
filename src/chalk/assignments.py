from datetime import datetime
from functools import partial, singledispatch
from pathlib import Path
from typing import Callable, Iterable

from .conf import SPREADSHEET_EXTENSIONS, STRUCTURED_DATA_EXTENSIONS, find_project_root
from .data import (
    load_spreadsheet,
    load_structured_data,
    save_spreadsheet,
    save_structured_data,
)
from .models import Assignment, AssignmentId, FileAssignment, SimpleAssignment
from .roster import read_roster
from .util import clean_data, clean_table, maybe_map

GRADE_ASSIGNMENT_EXTENSIONS = SPREADSHEET_EXTENSIONS | STRUCTURED_DATA_EXTENSIONS
ASSIGNMENT_IGNORE_LIST = {"__pycache__", ".DS_Store"}


def read_assignments(
    root: Path | None = None,
) -> Iterable[tuple[AssignmentId, Callable[[], Assignment]]]:
    """
    Read the assignments file and return a list of Assignment objects.
    """
    path = find_project_root(root) / "assignments"
    if not path.exists():
        return

    invalid = []
    for p in path.iterdir():
        p = p.resolve()

        if p.name in ASSIGNMENT_IGNORE_LIST or p.name.startswith("."):
            continue
        elif p.is_dir():
            yield (p.stem, partial(read_assignment, p))
        elif p.suffix in GRADE_ASSIGNMENT_EXTENSIONS:
            yield (p.stem, partial(read_assignment, p))
        else:
            invalid.append(p)

    if invalid:
        raise ValueError(f"Invalid assignment files: {', '.join(map(str, invalid))}")


def read_assignment(path: Path) -> Assignment:
    """
    Read the assignment file at the given path and return an Assignment object.
    """
    if path.is_dir():
        roster = read_roster()
        return read_directory_assignment(path, roster)
    elif path.suffix in GRADE_ASSIGNMENT_EXTENSIONS:
        return read_grade_assignment(path)
    else:
        raise ValueError(f"Invalid assignment file: {path}")


def read_grade_assignment(path: Path) -> SimpleAssignment:
    """
    Read the grade assignment file at the given path and return a GradeAssignment object.
    """
    match path.suffix:
        case ".csv" | ".xlsx":
            sheet = load_spreadsheet(path)
            return NotImplemented

        case ".json" | ".yaml" | ".yml":
            data = load_structured_data(path)
            if isinstance(data, list):
                msg = f"Grade assignment file {path} must contain a dictionary at the top level"
                raise ValueError(msg)
            data["path"] = path
            return SimpleAssignment.model_validate(data)

        case _:
            raise ValueError(f"Invalid grade assignment file: {path}")


def read_directory_assignment(path: Path, roster) -> FileAssignment:
    """
    Read the directory assignment at the given path and return a FileAssignment object.
    """
    if not path.is_dir():
        raise ValueError(f"Assignment path {path} is not a directory")

    files = {}
    for p in path.iterdir():
        if p.name in ASSIGNMENT_IGNORE_LIST or p.name.startswith("."):
            continue
        elif p.is_file():
            student_id = p.stem
            if student_id in roster:
                files[student_id] = p.resolve()
            else:
                raise ValueError(
                    f"Student ID {student_id} from file {p} not found in roster"
                )
        else:
            raise ValueError(f"Invalid file {p} in assignment directory {path}")

    return FileAssignment(id=path.name, files=files)


@singledispatch
def save_assignment(assignment: Assignment, split: bool = False, force: bool = False):
    """
    Add the given assignment to the assignments directory.
    """
    raise ValueError(f"Unsupported assignment type: {type(assignment)}")


@save_assignment.register
def save_simple_assignment(
    assignment: SimpleAssignment, split: bool = False, force: bool = False
):
    match assignment.path.suffix:
        case ".csv" | ".xlsx":
            sheet = []
            for student_id, entry in assignment.data.items():
                row = {
                    "id": student_id,
                    "start": maybe_map(datetime.isoformat, entry.start),
                    "end": maybe_map(datetime.isoformat, entry.end),
                }
                for q_id, response in entry.questions.items():
                    row.update(
                        {
                            f"{q_id}": response.answer,
                            f"{q_id}/grade": str(response.grade),
                            f"{q_id}/feedback": response.feedback,
                            f"{q_id}/start": maybe_map(
                                datetime.isoformat,
                                response.start,
                            ),
                            f"{q_id}.end": maybe_map(
                                datetime.isoformat,
                                response.end,
                            ),
                        }
                    )
                sheet.append(row)

            # Add the empty student with question ids and information
            row = {"id": ""}
            for q_id, q in (assignment.questions or {}).items():
                row.update(
                    {
                        f"{q_id}": q.name,
                        f"{q_id}/grade": str(q.grade),
                    }
                )
            sheet.insert(0, row)
            sheet = clean_table(sheet, keep={"id"})

            # Split the spreadsheet into separate files for each question if requested
            if split:
                split_by = ["grade", "feedback", "start", "end"]
            else:
                split_by = None

            save_spreadsheet(
                assignment.path,
                sheet,
                split_by=split_by,
                keep={"id"},
            )

        case ".json" | ".yaml" | ".yml":
            data = assignment.model_dump()
            del data["path"]
            data = clean_data(data)
            save_structured_data(assignment.path, data)
