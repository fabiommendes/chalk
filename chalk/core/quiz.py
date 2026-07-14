from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from functools import cached_property
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Literal,
    MutableSequence,
    cast,
)
from warnings import deprecated

import opt
import pandas as pd
import rich

from ..core.answer import AnyAnswer
from ..core.models import QuestionId, QuizId, StudentId
from ..core.submissions import Submissions
from ..data import dump_structured_data
from ..question import (
    Question,
    load_question,
)
from ..table import Table
from ..util.show import pretty_repr
from . import models
from .decimal import as_chalk_decimal
from .grades import Grades
from .student import Student

if TYPE_CHECKING:
    from .classroom import Classroom

__all__ = ["Quiz"]

QUIZ_IGNORE_LIST = {"__pycache__", "reports", "data", "scripts"}
DEFAULT_BACKUPS = 5


class Quiz:
    #
    # Properties
    #
    @property
    def classroom(self) -> Classroom:
        return self._classroom

    @property
    def name(self) -> str:
        return self._conf.name or self.id

    @property
    def autograder(self) -> models.Autograder:
        return self._conf.autograder or self.classroom.autograder

    @property
    def start(self) -> datetime | None:
        return self._conf.start

    @property
    def end(self) -> datetime | None:
        return self._conf.end

    @property
    def conf(self) -> models.Quiz:
        return self._conf

    @property
    def root(self) -> Path:
        return self.classroom.root / self.id

    @property
    def weight(self) -> Decimal:
        return opt.unwrap(self._conf.weight, Decimal(1))

    @cached_property
    def submissions(self) -> Submissions:
        path = self.root / "submissions.csv"
        if path.exists():
            submissions = Submissions.load(path, quiz=self)
        else:
            submissions = Submissions([], quiz=self)
        return submissions

    @cached_property
    def grades(self) -> Grades:
        path = self.root / "grades.csv"
        if path.exists():
            grades = Grades.load(path, quiz=self)
        else:
            grades = Grades([], quiz=self)
        return grades

    def __init__(self, id: QuizId, conf: models.Quiz, classroom: Classroom) -> None:
        self.id = id
        self._conf = conf
        self._classroom = classroom
        self._question_cache: dict[QuestionId, Question] = {}

    def __repr__(self) -> str:
        return pretty_repr(
            self,
            ["id", "path"],
            ["name", "start", "end", "questions"],
            keep_none=True,
        )

    #
    # Getters
    #
    def get_question(self, question_id: QuestionId, /) -> Question | None:
        """
        Get the question with the given id.

        If the question is not found in the quiz's questions, it will be
        created with the given id and returned.
        """
        if question_id in self._question_cache:
            return self._question_cache[question_id]

        if self._conf.questions is None:
            self._conf.questions = _find_questions_in_submissions(self)

        for conf in self._conf.questions:
            if conf.id == question_id:
                question = load_question(question_id, conf, quiz=self)
                self._question_cache[question_id] = question
                return question
        return None

    def get_questions(self) -> dict[QuestionId, Question]:
        """
        Get the questions for this quiz as a dictionary mapping question ids to Question objects.

        If the questions are not already loaded, they will be inferred from the submissions.
        """
        return {id: q for id in self.get_question_ids() if (q := self.get_question(id)) is not None}

    def get_question_ids(self) -> list[QuestionId]:
        """
        Get the question ids for this quiz as a list.

        If the questions are not already loaded, they will be inferred from the submissions.
        """
        if self._conf.questions is None:
            self._conf.questions = _find_questions_in_submissions(self)
        return [q.id for q in self._conf.questions]

    def get_answer(
        self, question: Question | QuestionId, student: Student | StudentId
    ) -> AnyAnswer | None:
        """
        Get the answer for the given question and student.
        """
        return self.submissions.get_answer(question=question, student=student)

    def get_autograder(self) -> models.Autograder:
        """
        Get the autograder configuration for this quiz, or a default configuration if none is set.
        """
        return self._conf.autograder or self.classroom.autograder or models.Autograder()

    def get_answers(self, question: Question | QuestionId) -> dict[StudentId, AnyAnswer]:
        """
        Get the answers for the given question as a dictionary mapping student ids to answers.
        """
        return dict(self.iter_answers(question))

    #
    # Iterators
    #
    def iter_answers(
        self,
        question: Question | QuestionId,
        /,
        *,
        inline_only: bool = False,
    ) -> Iterable[tuple[StudentId, AnyAnswer]]:
        """
        Iterate over the answers for the given question, yielding tuples of
        student id and answer.

        Args:
            question:
                The question or question id to get answers for.
            inline_only:
                If True, only return answers that were submitted in the
                submissions.csv file. Otherwise search for answers in files.
        """
        for student_id in self.classroom.get_roster():
            answer = self.submissions.get_answer(
                question=question,
                student=student_id,
                inline_only=inline_only,
            )
            if answer is None:
                continue
            yield student_id, answer

    #
    # Dataframes
    #
    @deprecated("Use quiz.grades.get_dataframe() instead.")
    def get_grades_dataframe(self, total: str | bool = False) -> pd.DataFrame:
        return self.grades.get_dataframe(total=total)

    @deprecated("Use Table.from_dataframe(quiz.grades.get_dataframe()) instead.")
    def get_grades_table(self, total: str | bool = False) -> Table[Decimal | None]:
        """
        Get the grades for all students and questions in this quiz.

        If total is provided, it will be added as a column with the sum of all
        question grades for each student.
        """

        return Table.from_dataframe(self.get_grades_dataframe(total=total))

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
            id: {
                "type": q.type,
                "grade": opt.unwrap(q.value, Decimal(1)),
                "name": q.name,
                "id": q.id,
            }
            for id, q in questions.items()
        }

        # Compute mean grade for each question if available
        acc_max: dict[QuestionId, Decimal] = defaultdict(Decimal)
        acc_sum: dict[QuestionId, Decimal] = defaultdict(Decimal)
        acc_sqr: dict[QuestionId, Decimal] = defaultdict(Decimal)
        acc_count: dict[QuestionId, int] = defaultdict(int)
        acc_skips: dict[QuestionId, int] = defaultdict(int)

        # FIXME:
        # for student_id, submission in self.iter_submissions():
        for student_id, submission in []:
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
            item["skip_rate"] = as_chalk_decimal(skip_rate)
            item["grade_max"] = acc_max[q_id]

            m2 = S2 / N if N > 0 else zero
            mean = S / N if N > 0 else zero
            item["grade_mean"] = mean = as_chalk_decimal(mean)
            item["grade_std"] = as_chalk_decimal((m2 - mean**2).sqrt())

        columns = "id name type grade grade_mean grade_max grade_std skip_rate".split()
        df = pd.DataFrame(data.values())[columns]
        df.set_index("id", inplace=True)

        return df

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
        Display details about the quiz to the console.
        """
        title = self.name or "Unnamed Quiz"
        rich.print(f"[b cyan]{title}[/] [dim]({self.id})[/]")
        if self.start:
            rich.print(f" - [b]Start:[/] {self.start.isoformat()}")
        if self.end:
            rich.print(f" - [b]End:[/] {self.end.isoformat()}")

        if self.get_questions():
            grades = Table.from_dataframe(self.grades.get_dataframe(total="_total"))
            totals = cast(list[Decimal], grades.get_column("_total"))

            grades_cell = None
            max_grade = None
            if totals:
                N = len(totals)
                max_grade = max(totals)
                mean = as_chalk_decimal(sum(totals) / N)
                s2 = sum((t**2 for t in totals), Decimal(0)) / N
                std = as_chalk_decimal((s2 - mean * mean).sqrt())
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
        Get a dictionary with basic information about the quiz.
        """

        df = self.question_statistics_dataframe()
        return {
            "id": self.id,
            "name": self.name,
            "start": self.start.isoformat() if self.start else None,
            "questions": len(self.get_question_ids()),
            "value": {
                "mean": df.grade_mean.sum(),
                "max": df.grade_max.sum(),
            },
        }

    def question_table(
        self, prec: int = 2, statistics: pd.DataFrame | None = None
    ) -> Table[str | None]:
        """
        Get a formatted table with question information for display.
        """

        def format_number(num: Decimal) -> str:
            return f"{num:.{prec}f}" if num.is_finite() else "N/A"

        def format_percent(num: Decimal) -> str:
            if not num.is_finite():
                return "N/A"
            pc = f"{100 * num:.{prec}f}"
            pc = pc.rstrip("0").removesuffix(".") or "0"
            return f"{pc}%"

        def format_grades(row: pd.Series[Any]) -> str:
            mean: Decimal = row["grade_mean"]
            std: Decimal = row["grade_std"]
            max: Decimal = row["grade"]
            percent: Decimal = mean / max if max > 0 else Decimal("nan")

            if not mean.is_finite() or not std.is_finite() or not max.is_finite():
                return "No grades"

            return f"{mean:.{prec}f} ± {std:.{prec}f} ({format_percent(percent)})"

        df = self.question_statistics_dataframe() if statistics is None else statistics
        df["grades"] = df.apply(format_grades, axis=1)
        df["value"] = df["grade"]
        df["skip rate"] = df["skip_rate"].apply(format_percent)
        df["max grade"] = df["grade_max"].apply(format_number)
        df = df[["name", "type", "value", "grades", "max grade", "skip rate"]]
        return Table.from_dataframe(df)

    def save(self) -> None:
        """
        Save the quiz to its path.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "conf.yaml"
        data = self._conf.model_dump(
            exclude_defaults=True,
            exclude_none=True,
            exclude_unset=True,
        )
        dump_structured_data(data, path, format="yaml")


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


def _find_questions_in_submissions(quiz: Quiz) -> list[models.Question]:
    """
    Find all questions in the submissions and return them as a dictionary.

    The question ids are inferred from the response keys in the submissions.
    """
    question_ids: set[QuestionId] = set()
    for submission in quiz.submissions.iter_submissions():
        question_ids.update(submission.responses.keys())

    return [models.GenericQuestion(id=q_id) for q_id in question_ids]
