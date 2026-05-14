from dataclasses import dataclass
from pathlib import Path

from . import conf
from .cli.util import from_dict_of_lists, to_dict_of_lists
from .data import load_spreadsheet
from .exceptions import ChalkError, Error
from .models import Student, StudentId
from .util import active_columns, clean_data, heuristic_map

COLUMN_ORDER = ["id", "name", "age", "email", "email_alt", "github"]


@dataclass
class Roster:
    path: Path | None
    data: dict[StudentId, Student]

    def __bool__(self):
        return bool(self.data)

    def __iter__(self):
        return iter(self.data.values())

    def __contains__(self, item):
        return item in self.data

    def model_dump(self):
        return [student.model_dump() for student in self.data.values()]


def read_roster() -> Roster:
    """
    Read the roster file at the given path and return a Roster object.
    """

    try:
        path = conf.get_roster_file()
    except ChalkError as e:
        if e.code == Error.ROSTER_NOT_FOUND:
            return Roster(data={}, path=None)
        raise

    data = map(Student.model_validate, load_spreadsheet(path))
    roster = {student.id: student for student in data}
    return Roster(data=roster, path=path)


HEURISTIC_COLUMNS = {
    "id",
    "name",
    "email",
    "email_alt",
    "github",
    "first_name",
    "last_name",
    "full_name",
}


def read_roster_like(path: Path) -> Roster:
    """
    Load a roster from a spreadsheet file and return a Roster object.

    This can be used to load arbitrary files that have the same information as the
    roster file. It is more flexible in the input formats it accepts and tries
    to be smart about how to interpret the data.
    """
    if not path.exists():
        raise Error.RESOURCE_NOT_FOUND(f"File {path} does not exist")

    raw_data = load_spreadsheet(path)
    columns = active_columns(raw_data)
    col_mapping = heuristic_map(columns, HEURISTIC_COLUMNS)

    adapted_data = {
        col_mapping.get(k, k): v for k, v in to_dict_of_lists(raw_data).items()
    }

    # We load data streams with separate first_name and last_name columns
    if (
        "first_name" in adapted_data
        and "last_name" in adapted_data
        and "name" not in adapted_data
    ):
        adapted_data["name"] = [
            f"{first} {last}"
            for first, last in zip(
                adapted_data["first_name"], adapted_data["last_name"]
            )
        ]

    data = map(Student.model_validate, from_dict_of_lists(adapted_data))
    roster = {student.id: student for student in data}
    return Roster(data=roster, path=path)


def save_roster(roster: Roster):
    """
    Save the roster to the roster file.
    """
    data = roster.model_dump()
    columns = {"id", *active_columns(data)}
    path = roster.path or conf.find_project_root() / "roster.csv"

    match path.suffix:
        case ".csv":
            _save_csv(path, data, columns)
        case ".json":
            import json

            path.write_text(json.dumps(clean_data(data), indent=2))
        case _:
            msg = f"Saving {path.suffix} roster is not implemented yet"
            raise NotImplementedError(msg)


def add_students(students: list[Student], force: bool = False):
    """
    Add new students to the roster.
    """
    roster = read_roster()
    for student in students:
        if student.id in roster and not force:
            raise Error.BAD_ROSTER(f"Student with ID {student.id} already exists")
        roster.data[student.id] = student

    save_roster(roster)


def update_student(student: Student):
    """
    Update a student in the roster.
    """
    roster = read_roster()
    if student.id not in roster.data:
        raise Error.BAD_ROSTER(f"Student with ID {student.id} does not exist")

    roster.data[student.id] = student
    save_roster(roster)


def _save_csv(path: Path, data: list[dict], columns: set[str]):
    import csv

    sorted_columns = sorted(columns, key=COLUMN_ORDER.index)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sorted_columns)
        writer.writeheader()
        writer.writerows(clean_data(data))
