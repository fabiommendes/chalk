from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    Iterable,
    Literal,
    Mapping,
    MutableSequence,
    cast,
    overload,
)

import errorz as rz
import natsort
import opt
import pandas as pd
import rich
from pydantic import BaseModel, Field, model_validator
from rich.prompt import Prompt

from ..data import (
    dump_spreadsheet,
    dump_structured_data,
    load_structured_data,
)
from ..question import (
    Generic,
    Question,
    question_id,
    validate_question,
)
from ..table import Table
from ..types import AssignmentId, QuestionId, StudentId
from ..util import clean_data
from ..util.decimal import normalize_decimal
from ..util.sequence import unique
from .classroom import SPREADSHEET_EXTENSIONS, STRUCTURED_DATA_EXTENSIONS
from .error import SystemError
from .grade import Grade
from .student import Student
from .submission import Response, Submission

if TYPE_CHECKING:
    from .classroom import Classroom
else:
    Classroom = Any  # type: ignore

__all__ = [
    "Assignment",
    "iter_assignments",
]


ASSIGNMENT_CONF_EXTENSIONS = STRUCTURED_DATA_EXTENSIONS
ASSIGNMENT_IGNORE_LIST = {"__pycache__", "reports", "data", "scripts"}


class Assignment(BaseModel):
    id: AssignmentId
    path: Path
    name: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    questions: dict[QuestionId, Question] | None = None
    submissions: dict[StudentId, Submission] | None = None
    classroom: Annotated[Classroom | None, Field(repr=False, exclude=True)] = None

    #
    # Constructors and loaders
    #
    @overload
    @classmethod
    def load(cls, *, path: Path) -> Assignment: ...

    @overload
    @classmethod
    def load(cls, *, id: AssignmentId) -> Assignment: ...

    @classmethod
    def load(
        cls, *, id: AssignmentId | None = None, path: Path | None = None
    ) -> Assignment:
        """
        Load an assignment by its id or path.

        Raise ChalkError if assignment is not found or if it is invalid.
        """
        if id is not None and path is not None:
            raise TypeError("Cannot specify both id and path")
        elif id is not None:
            return _read_assignment_by_id(id)
        elif path is not None:
            return _read_assignment_at(path)
        else:
            raise TypeError("Must specify either id or path")

    @classmethod
    def prompt(
        cls,
        assignment_id: str | None = None,
    ) -> Assignment:
        """
        Ask the user to select an assignment from the list of available assignments.
        """
        assignments = unique([id for id, _ in iter_assignments()])
        if not assignments:
            raise SystemError.RESOURCE_NOT_FOUND("No assignments found")
        if assignment_id is None and len(assignments) == 1:
            assignment_id = assignments[0]
        elif assignment_id is None:
            assignment_id = Prompt.ask("Assignment", choices=assignments)
        elif assignment_id not in assignments:
            raise SystemError.RESOURCE_NOT_FOUND(f"No assignment {assignment_id} found")
        return _read_assignment_by_id(assignment_id)

    #
    # Pydantic validators
    #
    @model_validator(mode="after")
    def _post_validation(self) -> Assignment:
        if self.questions is not None:
            for q in self.questions.values():
                q._assignment = self
        return self

    #
    # Properties
    #
    @property
    def base_path(self) -> Path:
        return self.path.parent

    #
    # Dataframes
    #
    def question_statistics_dataframe(self) -> pd.DataFrame:
        """
        Get a dataframe with question information.

        The dataframe will have the following columns:

        - id: the question id
        - name: the question name
        - type: the question type
        - grade: the question assigned grade
        - grade_mean: the mean grade for the question across all submissions
        - grade_std: the standard deviation of grades for the question across all submissions
        - grade_max: the maximum grade achieved for the question
        - skip_rate: the rate at which the question was skipped

        """
        questions = self.get_questions()
        data = {
            id: {"type": q.type, "grade": q.grade, "name": q.name, "id": q.id}
            for id, q in questions.items()
        }

        # Compute mean grade for each question if available
        acc_max: dict[QuestionId, Decimal] = defaultdict(Decimal)
        acc_sum: dict[QuestionId, Decimal] = defaultdict(Decimal)
        acc_sqr: dict[QuestionId, Decimal] = defaultdict(Decimal)
        acc_count: dict[QuestionId, int] = defaultdict(int)
        acc_skips: dict[QuestionId, int] = defaultdict(int)

        for student_id, submission in self.iter_submissions():
            for q_id, response in submission.responses.items():
                if response.grade is not None:
                    value = response.grade.value
                    acc_sum[q_id] += value
                    acc_sqr[q_id] += value**2
                    acc_count[q_id] += 1
                    acc_max[q_id] = max(acc_max[q_id], value)
                else:
                    acc_skips[q_id] += 1

        for q_id, item in data.items():
            S = acc_sum[q_id]
            S2 = acc_sqr[q_id]
            N = acc_count[q_id]
            N_skips = acc_skips[q_id]
            zero = Decimal(0)

            skip_rate = N_skips / (N + N_skips) if N + N_skips > 0 else 0.0
            item["skip_rate"] = normalize_decimal(skip_rate)
            item["grade_max"] = acc_max[q_id]

            m2 = S2 / N if N > 0 else zero
            mean = S / N if N > 0 else zero
            item["grade_mean"] = mean = normalize_decimal(mean)
            item["grade_std"] = normalize_decimal((m2 - mean**2).sqrt())

        columns = "id name type grade grade_mean grade_max grade_std skip_rate".split()
        df = pd.DataFrame(data.values())[columns]
        df.set_index("id", inplace=True)

        return df

    #
    # Iterators
    #
    def iter_submissions(self) -> Iterable[tuple[StudentId, Submission]]:
        """
        Iterate over the submissions for this assignment, yielding tuples of student id and submission.
        """
        if self.submissions is not None:
            yield from self.submissions.items()

    def _find_questions_in_submissions(self) -> dict[QuestionId, Question]:
        """
        Find all questions in the submissions and return them as a dictionary.

        The question ids are inferred from the response keys in the submissions.
        """
        question_ids: set[QuestionId] = set()
        for submission in (self.submissions or {}).values():
            question_ids.update(submission.responses.keys())

        return {q_id: Generic(id=q_id, _assignment=self) for q_id in question_ids}

    #
    # Display user info
    #
    def dump(
        self,
        path: Path | None = None,
        format: Literal["table", "csv", "json", "yaml"] | None = None,
        sort: Literal["id", "name", "grade", "value"] | None = None,
    ) -> None:
        """
        Display details about the assignment to the console.
        """
        title = self.name or "Unnamed Assignment"
        rich.print(f"[b cyan]{title}[/] [dim]({self.id})[/]")
        if self.start:
            rich.print(f" - [b]Start:[/] {self.start.isoformat()}")
        if self.end:
            rich.print(f" - [b]End:[/] {self.end.isoformat()}")

        if self.questions:
            grades = self.get_grades(total="_total")
            totals = cast(list[Decimal], grades.get_column("_total"))

            grades_cell = None
            max_grade = None
            if totals:
                N = len(totals)
                max_grade = max(totals)
                mean = normalize_decimal(sum(totals) / N)
                s2 = sum((t**2 for t in totals), Decimal(0)) / N
                std = normalize_decimal((s2 - mean * mean).sqrt())
                grades_cell = f"{mean} ± {std}"

            table = self.question_table()
            table.dump(
                path,
                format=format,
                sort=sort,
                last_row={
                    "id": "total",
                    "name": self.name,
                    "grades": grades_cell,
                    "max grade": max_grade,
                    "value": sum(table.get_column("value"), Decimal(0)),  # type: ignore
                },
                styles={"id": "bold yellow", "value": "bold blue"},
            )

    def info(self) -> dict[str, Any]:
        """
        Get a dictionary with basic information about the assignment.
        """

        df = self.question_statistics_dataframe()
        print(df)
        print(df.dtypes)
        return {
            "id": self.id,
            "name": self.name,
            "start": self.start.isoformat() if self.start else None,
            "questions": len(self.get_question_ids()),
            "submissions": opt.map(len, self.submissions),
            "grade": {
                "mean": df.grade_mean.sum(),
                "max": df.grade_max.sum(),
            },
        }

    #
    # Other
    #
    def get_question_ids(self) -> list[QuestionId]:
        """
        Get the list of question ids for this assignment.
        """
        if self.questions is not None:
            return list(self.questions.keys())

        question_ids: set[QuestionId] = set()
        for submission in (self.submissions or {}).values():
            question_ids.update(submission.responses.keys())
        return natsort.natsorted(question_ids)

    def get_questions(self) -> dict[QuestionId, Question]:
        """
        Get the questions for this assignment as a dictionary mapping question ids to Question objects.

        If the questions are not already loaded, they will be inferred from the submissions.
        """
        if self.questions is not None:
            return self.questions

        return self._find_questions_in_submissions()

    def get_grades(self, total: str | bool = False) -> Table[Grade | None]:
        """
        Get the grades for all students and questions in this assignment.

        If total is provided, it will be added as a column with the sum of all
        question grades for each student.
        """
        submissions = list(self.iter_submissions())

        grades = [
            {
                id: pd.NA if r.grade is None else r.grade.value
                for id, r in sub.responses.items()
            }
            for _, sub in submissions
        ]
        ids = [student_id for student_id, _ in submissions]
        df = pd.DataFrame(grades, index=ids)

        # Reorder columns according to the question ids in the assignment
        question_ids = self.get_question_ids()
        df = df.reindex(columns=question_ids)

        if total is True:
            total = "total"
        if total:
            df[total] = df.replace({pd.NA: 0, None: 0}).sum(axis=1)

        df.sort_index(inplace=True)
        return Table.from_dataframe(df)

    def get_submission(self, student: Student | StudentId) -> Submission | None:
        """
        Get the submission for the given student id.
        """
        student_id = student.id if isinstance(student, Student) else student
        if self.submissions is not None:
            return self.submissions.get(student_id)
        return None

    def get_response(
        self, student: Student | StudentId, question: Question | QuestionId
    ) -> Response | None:
        """
        Get the response for the given student id and question id.
        """
        submission = self.get_submission(student)
        if submission is None:
            return None

        return submission.responses.get(question_id(question))

    def get_question(self, question_id: QuestionId) -> Question | None:
        """
        Get the question with the given id.

        If the question is not found in the assignment's questions, it will be
        created with the given id and returned.
        """
        if self.questions is None:
            questions = self._find_questions_in_submissions()
        else:
            questions = self.questions
        return questions.get(question_id)

    def prompt_question(self, question_id: QuestionId | None = None) -> Question | None:
        """
        Prompt the user to select a question from the assignment.
        """
        if question_id is not None:
            return self.get_question(question_id)

        question_ids = self.get_question_ids()
        if not question_ids:
            return None
        question_id = Prompt.ask("Question", choices=question_ids)
        return self.get_question(question_id)

    def get_responses_for_question(
        self, question: Question | QuestionId
    ) -> dict[StudentId, Response]:
        """
        Get the responses for the given question id.

        This will return a dictionary mapping student ids to their responses for
        the given question id.
        """

        qid = question_id(question)
        responses = {}
        for student_id, submission in (self.submissions or {}).items():
            response = submission.responses.get(qid)
            if response is not None:
                responses[student_id] = response
        return responses

    def question_table(
        self, prec: int = 2, statistics: pd.DataFrame | None = None
    ) -> Table[str | None]:
        """
        Get a formatted table with question information for display.
        """

        def format_number(num: float) -> str:
            return f"{num:.{prec}f}" if not pd.isna(num) else "N/A"

        def format_percent(num: float) -> str:
            if pd.isna(num) or num is None:
                return "N/A"
            pc = f"{100 * num:.{prec}f}"
            pc = pc.rstrip("0").removesuffix(".") or "0"
            return f"{pc}%"

        def format_grades(row: pd.Series[float]) -> str:
            mean = row["grade_mean"]
            std = row["grade_std"]
            max = row["grade"]
            percent: float = mean / max if max > 0 else float("nan")

            if pd.isna(mean) or pd.isna(std) or pd.isna(max):
                return "No grades"

            return f"{mean:.{prec}f} ± {std:.{prec}f} ({format_percent(percent)})"

        df = self.question_statistics_dataframe() if statistics is None else statistics
        df["grades"] = df.apply(format_grades, axis=1)
        df["value"] = df["grade"]
        df["skip rate"] = df["skip_rate"].apply(format_percent)
        df["max grade"] = df["grade_max"].apply(format_number)
        df = df[["name", "type", "value", "grades", "max grade", "skip rate"]]
        return Table.from_dataframe(df)

    def save(self, split: bool = False, force: bool = False) -> None:
        """
        Save the assignment to its path.
        """
        match self.path.suffix:
            case ".csv" | ".xlsx":
                sheet = []
                for student_id, entry in (self.submissions or {}).items():
                    row = {
                        "id": student_id,
                        "start": opt.map(datetime.isoformat, entry.start),
                        "end": opt.map(datetime.isoformat, entry.end),
                    }
                    for q_id, response in entry.responses.items():
                        row.update(
                            {
                                f"{q_id}": opt.map(str, response.answer),
                                f"{q_id}.grade": str(response.grade),
                                f"{q_id}.feedback": response.feedback,
                                f"{q_id}.start": opt.map(
                                    datetime.isoformat,
                                    response.start,
                                ),
                                f"{q_id}.end": opt.map(
                                    datetime.isoformat,
                                    response.end,
                                ),
                            }
                        )
                    sheet.append(row)

                # Add the empty student with question ids and information
                empty_student: dict[str, str | None] = {"id": ""}
                for q_id, q in (self.questions or {}).items():
                    empty_student[q_id] = q.name
                    empty_student[f"{q_id}.grade"] = (
                        str(q.grade) if q.grade is not None else None
                    )

                sheet.insert(0, empty_student)
                clean_sheet = Table(sheet)

                # Split the spreadsheet into separate files for each question if requested
                if split:
                    split_by = ["grade", "feedback", "start", "end"]
                else:
                    split_by = None

                dump_spreadsheet(
                    self.path,
                    clean_sheet,
                    split_by=split_by,
                    keep=["id"],
                )

            case ".json" | ".yaml" | ".yml":
                data = self.model_dump()
                del data["path"]
                data = clean_data(data)
                dump_structured_data(
                    data,
                    self.path,
                )

            case _:
                msg = f"Unsupported assignment file format: {self.path.suffix}"
                raise ValueError(msg)


def iter_assignments(
    root: Path | None = None,
) -> Iterable[tuple[AssignmentId, Callable[[], Assignment]]]:
    """
    Read the assignments file and return a list of Assignment objects.
    """
    from ..conf import find_project_root

    root = find_project_root(root)
    if not root.exists():
        return

    for path in natsort.natsorted(root.iterdir(), key=lambda p: p.stem):
        if (conf := assignment_compatible_path(path)) is not None:
            yield conf.parent.name, partial(_read_assignment_at, conf)


def _read_assignment_by_id(
    assignment_id: AssignmentId, /, root: Path | None = None
) -> Assignment:
    """
    Read the assignment with the given id and return it as an Assignment object.
    """
    for aid, reader in iter_assignments(root):
        if aid == assignment_id:
            return reader()

    raise SystemError.RESOURCE_NOT_FOUND(f"No assignment with id {assignment_id} found")


def _read_assignment_at(path: Path, /) -> Assignment:
    """
    Read the assignment file at the given path and return an Assignment object.
    """
    match path.suffix:
        case ".json" | ".yaml" | ".yml" if path.is_file():
            data = load_structured_data(path)
            if isinstance(data, list):
                msg = f"Grade assignment file {path} must contain a dictionary at the top level"
                raise ValueError(msg)
            data["path"] = path
            data["id"] = path.stem
            return Assignment.model_validate(data)

        case _ if path.is_dir():
            raise NotImplementedError

        case _:
            raise ValueError(f"Invalid grade assignment file: {path}")


def pop_template_row[T](
    sheet: MutableSequence[dict[str, T]],
) -> dict[str, T] | None:
    """
    If the first row of the sheet has an empty "id" column, pop it and return it as a template.
    """
    if not sheet:
        return None
    for i, row in enumerate(sheet):
        if "id" not in row:
            raise ValueError("Spreadsheet must have an 'id' column")
        if not row["id"]:
            return sheet.pop(i)
    return None


STANDARD_COLUMNS = {"id", "name", "age", "email", "email_alt", "github"}


def read_questions[T](template: Mapping[str, T]) -> list[Question]:
    """
    Read the question information from the template row and return a list of Question objects.
    """
    questions: dict[str, dict[str, T]] = defaultdict(dict)
    for key, value in template.items():
        if key in STANDARD_COLUMNS:
            continue

        if "." not in key:
            q_id = key
            field = "name"
        else:
            q_id, field, *rest = key.rsplit(".", 1)
            if rest:
                raise ValueError(f"Invalid question field: {key}")

        questions[q_id]["id"] = cast(T, q_id)
        questions[q_id][field] = value

    return [validate_question(q) for q in questions.values()]


def assignment_compatible_path(path: Path) -> Path | None:
    """
    Return True if the path is an assignment directory.
    """
    from . import validate_assignment_id

    # Invalidate the following conditions:
    if not path.is_dir():
        return None
    if path.name.startswith(".") or path.name.startswith("_"):
        return None
    if path.name in ASSIGNMENT_IGNORE_LIST:
        return None
    if not rz.call_checked(ValueError, validate_assignment_id, path.name):
        return None

    # Only accept valid folder names with a /conf.{yaml|json} file
    for conf in path.glob("conf.*"):
        if conf.suffix in ASSIGNMENT_CONF_EXTENSIONS:
            return conf

    return None


def path_priority(path: Path) -> int:
    """
    Return the priority of the path for selecting among multiple files with the same stem.

    Directories have higher priority than files, and among files, those with more common assignment extensions have higher priority.
    """
    if path.suffix in STRUCTURED_DATA_EXTENSIONS:
        return 0
    elif path.suffix in SPREADSHEET_EXTENSIONS:
        return 1
    elif path.is_dir():
        return 2
    else:
        return 3
