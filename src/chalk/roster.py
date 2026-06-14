import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Literal, Mapping

from rich.prompt import Prompt

from . import conf
from .core import ChalkError, Student, StudentId, SystemError
from .data import load_spreadsheet
from .table import Table
from .util import clean_data, from_dict_of_lists, heuristic_map

__all__ = ["Roster", "read_roster", "read_roster_like", "ConflictMode", "MergeConflict"]

COLUMN_ORDER = ["id", "name", "age", "email", "email_alt", "github"]

type Json = dict[str, Any] | list[Any]
type JsonValue = Json | str | int | float | bool | None
type MergeConflict = str  # FIXME: Define an structured conflict object
type ConflictMode = Literal["merge", "keep", "replace"]


@dataclass
class Roster(Mapping[StudentId, Student]):
    path: Path | None
    data: dict[StudentId, Student]

    def __bool__(self) -> bool:
        return bool(self.data)

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def __contains__(self, item: Any) -> bool:
        return item in self.data

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, key: StudentId) -> Student:
        return self.data[key]

    def model_dump(self) -> dict[StudentId, dict[str, str | None]]:
        return {id: student.model_dump() for id, student in self.data.items()}

    def table(self) -> Table[str | None]:
        data = self.model_dump().values()
        columns = ["name", "email", "email_alt", "github"]
        ids = [item["id"] or "" for item in data]
        rows = [[item.get(col) for col in columns] for item in data]
        return Table(rows, index=ids, columns=columns)

    def fuzzy_match_student_id(self, student_id: str) -> StudentId | None:
        """
        Fuzzy match the given student ID to a student in the roster.

        Return the best matching student ID (or None if no match is found).
        """
        student_id = student_id.strip()
        if student_id in self.data:
            return student_id

        field_map: dict[str, list[StudentId]] = defaultdict(list)
        substring = student_id.casefold()

        for student in self.data.values():
            for key in ["id", "name", "email", "email_alt", "github"]:
                field_data = getattr(student, key)
                if field_data is None:
                    continue
                field_data = str(field_data).casefold()
                if substring in field_data:
                    field_map[field_data].append(student.id)

        matches = Counter(id for ids in field_map.values() for id in ids)
        if not matches:
            return None
        best_match, _ = matches.most_common(1)[0]
        return best_match

    def prompt_student(self, student_id: str | None) -> Student | None:
        """
        Prompt the user to select a student from the roster.

        If student_id is provided, it will be normalized and used as the default value.
        """
        if student_id is None:
            student_id = Prompt.ask("Enter student ID or name")
        student_id = self.fuzzy_match_student_id(student_id)

        if student_id is None:
            return None
        try:
            return self.data[student_id]
        except KeyError:
            return None

    def add_students(
        self,
        students: list[Student],
        conflict: ConflictMode = "merge",
    ) -> list[MergeConflict]:
        """
        Add new students to the roster.
        """
        conflicts: list[str] = []
        roster = read_roster()

        for student in students:
            if student.id not in roster:
                self.data[student.id] = student
            elif student.can_merge_with(roster[student.id]):
                # Preference to the old student data when merging.
                self.data[student.id] = student.merge_with(roster[student.id])
                conflicts.append(f"merge {student.id}")
            elif conflict == "replace":
                self.data[student.id] = student
                conflicts.append(f"replace {student.id}")
            elif conflict == "keep":
                conflicts.append(f"keep {student.id}")
            else:
                conflicts.append(f"conflict {student.id}")

        self.save()
        return conflicts

    def save(self) -> None:
        """
        Save the roster to the roster file.
        """
        table = self.table()
        columns = {"id", *table.columns}
        path = self.path or conf.find_project_root() / "roster.csv"

        match path.suffix:
            case ".csv":
                data = table.to_dicts()
                _save_csv(path, data, columns)
            case ".json":
                data = table.to_dicts(clear_nones=True)
                path.write_text(json.dumps(data, indent=2))
            case _:
                msg = f"Saving {path.suffix} roster is not implemented yet"
                raise NotImplementedError(msg)


def read_roster() -> Roster:
    """
    Read the roster file at the given path and return a Roster object.
    """

    try:
        path = conf.get_roster_file()
    except ChalkError as e:
        if e.reason == SystemError.ROSTER_NOT_FOUND:
            return Roster(data={}, path=None)
        raise

    table = load_spreadsheet(path)
    data = [Student.model_validate({"id": id, **d}) for id, d in table.items()]
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
        raise SystemError.RESOURCE_NOT_FOUND(f"File {path} does not exist")

    table = load_spreadsheet(path)
    columns = table.active_columns()
    col_mapping = heuristic_map(columns, HEURISTIC_COLUMNS)
    adapted_data = {col_mapping.get(k, k): v for k, v in table.iter_columns()}

    # We load data streams with separate first_name and last_name columns
    if (
        "first_name" in adapted_data
        and "last_name" in adapted_data
        and "name" not in adapted_data
    ):
        adapted_data["name"] = [
            f"{first} {last}"
            for first, last in zip(
                adapted_data["first_name"],
                adapted_data["last_name"],
            )
        ]

    data = map(Student.model_validate, from_dict_of_lists(adapted_data))
    roster = {student.id: student for student in data}
    return Roster(data=roster, path=path)


def _save_csv(path: Path, data: list[dict[str, Any]], columns: set[str]) -> None:
    import csv

    sorted_columns = sorted(columns, key=COLUMN_ORDER.index)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sorted_columns)
        writer.writeheader()
        writer.writerows(clean_data(data))
