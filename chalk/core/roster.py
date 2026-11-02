from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Iterator,
    Literal,
    Mapping,
    assert_never,
)

from rich.prompt import Prompt

from ..data import load_spreadsheet
from ..table import Table
from ..util import clean_data, from_dict_of_lists, heuristic_map
from .models import StudentId
from .student import Student

if TYPE_CHECKING:
    from .classroom import Classroom

__all__ = ["Roster", "read_roster_like"]

#: Columns of the roster file shared with codehood, in order. See
#: design/mdq-e-roster.md.
SHARED_COLUMNS = ["school_id", "username", "name", "email", "github", "status"]
COLUMN_ORDER = ["id", *SHARED_COLUMNS, "age", "email_alt"]
DEFAULT_ID_COLUMN = "school_id"
type ConflictMode = Literal["merge", "replace", "keep", "error"]
type MergeConflict = str


@dataclass(frozen=True)
class Roster(Mapping[StudentId, Student]):
    """
    The students of a classroom, read from roster.csv.

    The file may be shared with other tools (codehood), so the roster keeps
    what it does not use: the order of the columns and the rows that have no
    student id. Both are written back by `save`.
    """

    path: Path
    data: dict[StudentId, Student]

    #: Column of the roster file that holds the student id.
    id_column: str = DEFAULT_ID_COLUMN

    #: Columns of the file, in the order they were read.
    columns: tuple[str, ...] = ()

    #: Rows with no student id, kept as they were read.
    orphans: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_json(
        cls,
        items: Iterable[Mapping[str, str | None]],
        /,
        path: Path,
        classroom: Classroom,
        id_column: str | None = None,
    ) -> Roster:
        """
        Load roster from a JSON-like iterable of dictionaries and return a Roster object.

        Args:
            id_column:
                Column with the student id. By default, use "school_id" if
                present, otherwise "id".
        """
        items = [dict(item) for item in items]
        columns: list[str] = []
        for item in items:
            columns.extend(k for k in item if k not in columns)

        if id_column is None:
            id_column = DEFAULT_ID_COLUMN if DEFAULT_ID_COLUMN in columns or not columns else "id"
        if items and id_column not in columns:
            raise ValueError(f"Roster file has no {id_column!r} column: {path}")

        data: dict[StudentId, Student] = {}
        orphans: list[dict[str, Any]] = []
        for item in items:
            id = (item.get(id_column) or "").strip()
            if not id:
                orphans.append(item)
                continue
            if id in data:
                raise ValueError(f"Duplicate student id in {path}: {id!r}")

            fields = {k: v for k, v in item.items() if k not in (id_column, "name")}
            name = (item.get("name") or "").strip() or id
            data[id] = Student(id, name, classroom=classroom, **clean_data(fields))

        return cls(
            data=data,
            path=path,
            id_column=id_column,
            columns=tuple(columns),
            orphans=tuple(orphans),
        )

    def to_json(self) -> list[dict[str, Any]]:
        """
        Convert the roster to a list of dictionaries suitable for JSON serialization.
        """
        return [
            {"id": student.id, "name": student.name, **student.extra}
            for student in self.data.values()
        ]

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

    def get_fuzzy(self, label: str, max_matches: int = 5) -> list[Student]:
        """
        Fuzzy match the given student ID to students in the roster.

        Return a list of matching students (or an empty list if no match is found).
        """
        # Weight of the match relative to generic fields in student.extra
        ID_WEIGHT = 10
        NAME_WEIGHT = 5

        label = label.strip()

        # Try exact match using id
        if label in self.data:
            return [self.data[label]]

        # Try case insensitive match using id
        for student in self.data.values():
            if label.casefold() == student.id.casefold():
                return [student]

        # Try substring match using id or name
        matches: Counter[str] = Counter()
        for student in self.data.values():
            sub = label.casefold()
            if sub in student.id.casefold():
                matches[student.id] += ID_WEIGHT
            if sub in student.name.casefold():
                matches[student.id] += NAME_WEIGHT

        # Search in other fields
        if not matches:
            sub = label.casefold()
            for student in self.data.values():
                for v in student.extra.values():
                    if isinstance(v, str) and sub in v.casefold():
                        matches[student.id] += 1
                        break

        most_common = matches.most_common(max_matches)
        return [self.data[id] for id, _ in most_common]

    def table(self) -> Table[str | None]:
        """
        Table representation of roster data.
        """
        col_set = {"id", "name"}
        data: list[dict[str, str]] = []

        for student in self.data.values():
            row = {"id": student.id, "name": student.name}
            row.update(student.extra)
            col_set.update(row.keys())
            data.append(row)

        col_set.discard("id")
        columns = sorted(sorted(col_set), key=_column_order)
        ids = [item.pop("id") for item in data]
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

        Return a list of conflicts, if any, that occurred during the merge process.
        """
        conflicts: list[str] = []
        data = self.data.copy()

        for student in students:
            if student.id not in self:
                data[student.id] = student
                continue

            match conflict:
                case "error":
                    raise ValueError(f"Cannot merge: {student.id}")
                case "merge":
                    merged = student & data[student.id]
                    if merged is not None:
                        data[student.id] = merged
                case "replace":
                    data[student.id] = student
                case "keep":
                    pass
                case _:
                    assert_never(conflict)

        self.data.clear()
        self.data.update(data)
        return conflicts

    def save(self) -> None:
        """
        Save the roster to the roster file.
        """
        rows = [
            {self.id_column: student.id, "name": student.name, **student.extra}
            for student in self.data.values()
        ]
        rows.extend(self.orphans)

        columns = list(self.columns) or [self.id_column, *SHARED_COLUMNS[1:3]]
        for row in rows:
            columns.extend(k for k in row if k not in columns)

        path = self.path
        match path.suffix:
            case ".csv":
                _save_csv(path, rows, columns)
            case ".json":
                path.write_text(json.dumps(clean_data(rows), indent=2, ensure_ascii=False))
            case _:
                msg = f"Saving {path.suffix} roster is not supported"
                raise ValueError(msg)


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


def read_roster_like(path: Path, classroom: Classroom) -> Roster:
    """
    Load a roster from a spreadsheet file and return a Roster object.

    This can be used to load arbitrary files that have the same information as the
    roster file. It is more flexible in the input formats it accepts and tries
    to be smart about how to interpret the data.
    """
    if not path.exists():
        raise FileNotFoundError(f"Roster file not found: {path}")

    table = load_spreadsheet(path)
    columns = table.active_columns()
    col_mapping = heuristic_map(columns, HEURISTIC_COLUMNS)
    adapted_data = {col_mapping.get(k, k): v for k, v in table.iter_columns()}

    # We load data streams with separate first_name and last_name columns
    if "first_name" in adapted_data and "last_name" in adapted_data and "name" not in adapted_data:
        adapted_data["name"] = [
            f"{first} {last}"
            for first, last in zip(
                adapted_data["first_name"],
                adapted_data["last_name"],
            )
        ]

    data = (Student.from_json(x, classroom=classroom) for x in from_dict_of_lists(adapted_data))
    roster = {student.id: student for student in data}
    return Roster(data=roster, path=path)


def _save_csv(path: Path, data: list[dict[str, Any]], columns: list[str]) -> None:
    import csv

    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


def _column_order(column: str) -> int:
    try:
        return COLUMN_ORDER.index(column)
    except ValueError:
        return len(COLUMN_ORDER)
