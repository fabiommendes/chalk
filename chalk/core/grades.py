from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Callable, Iterable
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Literal,
    NamedTuple,
    cast,
    overload,
)
from warnings import deprecated
from weakref import ref

import opt
import pandas as pd
from pydantic import ValidationError
from pydantic_core import InitErrorDetails
from rich.console import Console, RenderableType

from ..data.protocols import get_id
from ..table import Table
from ..util import unpack
from ..util.dataframe import ALL_STATS, DEFAULT_STATS, Stats, grades_dataframe_stats
from . import models
from .decimal import chalk_decimal, render_decimal
from .disqualification import Disqualification, is_disqualification
from .models import QuestionId, StudentId
from .score import MAX_SCORE, MIN_SCORE, Score, mul, score

if TYPE_CHECKING:
    from ..question import Question
    from .classroom import Classroom
    from .quiz import Quiz
    from .student import Student

NOT_GIVEN: Any = object()

# Render some special fractions as decimals
RENDERED_COMMON_FRACTIONS = {
    **{Fraction(i, 100): f"0.0{i}" for i in range(1, 10) if i % 10 != 0},
    **{Fraction(i, 100): f"0.{i}" for i in range(10, 100) if i % 10 != 0},
    **{Fraction(i, 10): f"0.{i}0" for i in range(1, 10)},
    Fraction(0): "0.00",
    Fraction(1, 4): "0.25",
    Fraction(1, 2): "0.50",
    Fraction(3, 4): "0.75",
    Fraction(1): "1.00",
}
RENDERED_COMMON_FRACTIONS_INV = {v: k for k, v in RENDERED_COMMON_FRACTIONS.items()}


type Field = str

#: Rows of the grades file besides the score, one per student that has them.
EXTRA_FIELDS = ("feedback", "notes")
type _SubmissionsIter = Iterable[tuple[StudentId, models.SubmissionGrade]]
type _ResponsesIter = Iterable[tuple[QuestionId, models.ResponseGrade]]


class StudentQuestionGrade[T](NamedTuple):
    student: StudentId
    question: QuestionId
    grade: T


ZERO_SCORE = score(0)
ONE_SCORE = score(1)


class Grades:
    """
    A collection of grades for a quiz.

    It behaves like a mapping from (student_id, question_id) to a score or disqualification.
    """

    #
    # Properties
    #
    @property
    def quiz(self) -> Quiz:
        return unpack(self._quiz(), throw=RuntimeError("Quiz reference is dead"))

    @property
    def classroom(self) -> Classroom:
        return self.quiz.classroom

    #
    # Constructors
    #
    @classmethod
    def load(cls, path: Path, quiz: Quiz) -> Grades:
        """
        Load Grades from a tabular format (e.g., CSV, Excel) at the given path.
        """
        return load_grades_from_path(path, quiz)

    def __init__(self, grades: Iterable[models.SubmissionGrade], quiz: Quiz) -> None:
        self._grades = {s.id: s for s in grades}
        self._quiz = ref(quiz)

        # Store all questions that have associated responses
        self._graded_questions: set[QuestionId] = set()
        for submission in grades:
            self._graded_questions.update(submission.responses.keys())

    #
    # IO
    #
    def save(self, path: Path | None = None):
        """
        Save grades .csv file to the given (or the default) path.
        """
        if path is None:
            path = self.quiz.root / "grades.csv"

        file = io.StringIO()
        save_grades_to_path(self._grades, file, self.quiz.get_question_ids())
        path.write_text(file.getvalue())

    def render(
        self,
        *,
        title: str | None = None,
        sort: QuestionId = "id",
        stats: Iterable[Stats] = DEFAULT_STATS,
        total: str | bool = "total",
    ) -> RenderableType:
        """
        Render the grades as a table.
        """
        df = self.get_dataframe(total=total)
        table = Table.from_dataframe(df)

        extra_rows: list[dict[str, Any]] = []
        if stats:
            stats = list(stats)
            if not all(stat in ALL_STATS for stat in stats):
                raise ValueError(f"Invalid stats: {stats}. Valid stats are: {ALL_STATS}")
            stats_df = grades_dataframe_stats(df)

            for stat in stats:
                data = cast(dict[str, Any], stats_df[stat].to_dict())
                extra_rows.append({"id": stat, **data})

        return table.render(
            styles={"id": "bold yellow", "total": "bold blue"},
            title=title.format(quiz=self.quiz) if title else None,
            empty="No grades available",
            sort=sort,
            extra_rows=extra_rows,
        )

    def __rich__(self) -> RenderableType:
        return self.render()

    def __str__(self) -> str:
        file = io.StringIO()
        console = Console(file=file)
        console.print(self.render())
        return file.getvalue()

    #
    # Getters and setters
    #
    @overload
    def get_score(
        self,
        *,
        question: QuestionId | Question,
        student: StudentId | Student,
        disqualified: Score | Literal[0, 1],
    ) -> Score | None: ...

    @overload
    def get_score(
        self,
        *,
        question: QuestionId | Question,
        student: StudentId | Student,
        disqualified: Score | Literal[0, 1] | None = None,
    ) -> Score | Disqualification | None: ...

    def get_score(
        self,
        *,
        question: QuestionId | Question,
        student: StudentId | Student,
        disqualified: Score | Literal[0, 1] | None = None,
    ) -> Score | Disqualification | None:
        """
        Get the grade for a given question and student.

        Args:
            question:
                The question or question id to get grades for.
            student:
                The student or student id to get grades for.
        """
        question_id = get_id(question)
        student_id = get_id(student)

        try:
            value = self._grades[student_id].responses[question_id].score
        except KeyError:
            return None
        else:
            if isinstance(value, Disqualification) and disqualified is not None:
                if disqualified == 0:
                    return ZERO_SCORE
                elif disqualified == 1:
                    return ONE_SCORE
                else:
                    return disqualified
            return value

    def get_grade(
        self,
        *,
        question: QuestionId | Question,
        student: StudentId | Student,
        disqualified: Score = MIN_SCORE,
    ) -> Score | None:
        """
        Get the grade for a given question and student.
        """
        value = self.get_score(question=question, student=student, disqualified=disqualified)
        if value is None:
            return None
        if isinstance(question, QuestionId):
            question = unpack(
                self.quiz.get_question(question),
                throw=ValueError(f"Invalid question id: {question}"),
            )

        return mul(value, question.value)

    def set_score(
        self,
        score: Score | Disqualification,
        *,
        question: QuestionId | Question,
        student: StudentId | Student,
        feedback: str | None = NOT_GIVEN,
        adjustments: list[models.Adjustment] | None = NOT_GIVEN,
        notes: str | None = NOT_GIVEN,
    ) -> None:
        """
        Save score for the given question and student.
        """
        question_id = get_id(question)
        student_id = get_id(student)

        submission = self._grades.setdefault(
            student_id,
            models.SubmissionGrade(id=student_id, responses={}),
        )
        response = submission.responses.setdefault(
            question_id,
            models.ResponseGrade(score=score),
        )
        response.score = score

        if feedback is not NOT_GIVEN:
            response.feedback = feedback
        if adjustments is not NOT_GIVEN:
            response.adjustments = adjustments
        if notes is not NOT_GIVEN:
            response.notes = notes

    def get_dataframe(self, total: str | bool = False) -> pd.DataFrame:
        """
        Return a dataframe with the grades for all students and questions in
        this quiz.

        The dataframe contains Decimal values.
        """
        rows: dict[StudentId, dict[QuestionId, Decimal]] = defaultdict(dict)

        for student_id, question_id, grade in self.iter_grades():
            if grade is not None:
                rows[student_id][question_id] = grade

        index = sorted(rows.keys())
        values = [rows[student_id] for student_id in index]

        df = pd.DataFrame.from_records(
            values,
            index=index,
            columns=list(self.quiz.get_question_ids()),
        )
        if total is True:
            total = "total"
        if total:
            df[total] = df.replace({pd.NA: 0, None: 0}).sum(axis=1)
        return df

    #
    # Iterators
    #
    @overload
    def iter_scores(
        self,
        *,
        question: QuestionId | Question,
        disqualified: Literal["min", "max"] | Score | None,
    ) -> Iterable[tuple[StudentId, Score | None]]: ...

    @overload
    def iter_scores(
        self,
        *,
        question: QuestionId | Question,
        disqualified: Literal["keep"] = "keep",
    ) -> Iterable[tuple[StudentId, Score | Disqualification | None]]: ...

    @overload
    def iter_scores(
        self,
        *,
        student: StudentId | Student,
        disqualified: Literal["min", "max"] | Score | None,
    ) -> Iterable[tuple[QuestionId, Score | None]]: ...

    @overload
    def iter_scores(
        self,
        *,
        student: StudentId | Student,
        disqualified: Literal["keep"] = "keep",
    ) -> Iterable[tuple[QuestionId, Score | Disqualification | None]]: ...

    def iter_scores(
        self,
        *,
        question: QuestionId | Question | None = None,
        student: StudentId | Student | None = None,
        disqualified: Literal["keep", "min", "max"] | Score | None = "keep",
    ) -> Iterable[tuple[Any, Score | Disqualification | None]]:
        """
        Iterate over all scores.

        This method allow filtering by question or student.

        Args:
            question:
                The question or question id to filter scores by.
            student:
                The student or student id to filter scores by.
            disqualified:
                How to handle disqualified scores. If "keep", keep the disqualification.
                If "min", replace disqualified scores with the minimum score (0).
                If "max", replace disqualified scores with the maximum score (1).
                If a Score is provided, replace disqualified scores with that score.
        """
        if disqualified == "keep":
            disqualified_fn = lambda x: x
        elif disqualified == "min":
            disqualified_fn = lambda x: MIN_SCORE
        elif disqualified == "max":
            disqualified_fn = lambda x: MAX_SCORE
        else:
            disqualified_fn = lambda x: disqualified

        if question is None and student is None:
            raise TypeError("one of question or student must be specified")

        if question is not None:
            qid = get_id(question)
            yield from self._iter_question_scores(qid, disqualified_fn)

        if student is not None:
            sid = get_id(student)
            yield from self._iter_student_scores(sid, disqualified_fn)

    def _iter_question_scores(
        self,
        question_id: QuestionId,
        disqualified_fn: Callable[[Disqualification], Score | None],
    ) -> Iterable[tuple[StudentId, Any]]:
        question_id = get_id(question_id)
        for student_id, submission in self._grades.items():
            for qid, response in submission.responses.items():
                if qid != question_id:
                    continue

                score = response.score
                if isinstance(score, Disqualification):
                    yield student_id, disqualified_fn(score)
                else:
                    yield student_id, score

    def _iter_student_scores(
        self,
        student_id: StudentId,
        disqualified_fn: Callable[[Disqualification], Score | None],
    ) -> Iterable[tuple[QuestionId, Any]]:

        submission = self._grades.get(student_id)
        if submission is None:
            return

        for qid, response in submission.responses.items():
            score = response.score
            if isinstance(score, Disqualification):
                yield qid, disqualified_fn(score)
            else:
                yield qid, score

    @deprecated("iter_all_scores is deprecated, use iter_scores instead")
    @overload
    def iter_all_scores(
        self,
        *,
        skip_disqualified: Literal[True],
        question: QuestionId | Question | None = None,
        student: StudentId | Student | None = None,
        skip_missing: bool = False,
    ) -> Iterable[StudentQuestionGrade[Score | None]]: ...

    @deprecated("iter_all_scores is deprecated, use iter_scores instead")
    @overload
    def iter_all_scores[T](
        self,
        *,
        disqualified: T,
        question: QuestionId | Question | None = None,
        student: StudentId | Student | None = None,
        skip_missing: bool = False,
    ) -> Iterable[StudentQuestionGrade[Score | T | None]]: ...

    def iter_all_scores[T](
        self,
        *,
        question: QuestionId | Question | None = None,
        student: StudentId | Student | None = None,
        skip_missing: bool = False,
        **kwargs: Any,
    ) -> Iterable[StudentQuestionGrade[Any]]:
        """
        Iterate over all scores for a given question.

        Args:
            question, student:
                Filter scores for an specific question or student.
            disqualified:
                The value to use for disqualified scores.
        """
        question_id = opt.map(get_id, question)
        only_student = opt.map(get_id, student)

        skip_disqualified = kwargs.get("skip_disqualified", False)
        if kwargs and "disqualified" in kwargs:
            default_disqualified = kwargs["disqualified"]
            update_disqualified = True
        else:
            default_disqualified = NotImplemented
            update_disqualified = False

        students = set(self.classroom.roster.keys())
        for student_id, submission in self._iter_submissions(only_student):
            students.discard(student_id)

            for qid, response in self._iter_responses(question_id, submission):
                grade = response.score
                if isinstance(grade, Disqualification):
                    if update_disqualified:
                        grade = default_disqualified
                    elif skip_disqualified:
                        continue

                yield StudentQuestionGrade(student_id, qid, grade)

        if skip_missing:
            return

        if only_student is not None:
            students &= {only_student}
        questions = self.quiz.get_question_ids()
        for student_id in sorted(students):
            for qid in questions:
                if question_id is not None and qid != question_id:
                    continue
                yield StudentQuestionGrade(student_id, qid, None)

    @overload
    def iter_grades(
        self,
        *,
        skip_disqualified: Literal[True],
        question: QuestionId | Question | None = None,
        student: StudentId | Student | None = None,
    ) -> Iterable[StudentQuestionGrade[Decimal | None]]: ...

    @overload
    def iter_grades[T](
        self,
        *,
        disqualified: Decimal = Decimal(0),
        question: QuestionId | Question | None = None,
        student: StudentId | Student | None = None,
    ) -> Iterable[StudentQuestionGrade[Decimal | None]]: ...

    @overload
    def iter_grades(
        self,
        *,
        question: QuestionId | Question | None = None,
        student: StudentId | Student | None = None,
        **kwargs: Any,
    ) -> Iterable[StudentQuestionGrade[Decimal | None]]: ...

    def iter_grades(self, **kwargs: Any) -> Iterable[StudentQuestionGrade[Decimal | None]]:
        """
        Iterate over all grades for a given question.

        Args:
            question, student:
                Filter grades for a specific question or student.
            disqualified:
                The value to use for disqualified grades. (default = 0)
            skip_disqualified:
                If True, skip disqualified grades.
        """
        question_values = {qid: q.value for qid, q in self.quiz.get_questions().items()}
        if "disqualified" not in kwargs:
            kwargs["disqualified"] = Decimal(0)

        for sid, qid, qscore in self.iter_all_scores(**kwargs):
            try:
                qvalue = question_values[qid]
            except KeyError:
                continue

            if qscore is None:
                yield StudentQuestionGrade(sid, qid, None)
            else:
                grade = compute_grade(qscore, qvalue)
                yield StudentQuestionGrade(sid, qid, grade)

    @overload
    def update_score(
        self, updates: dict[QuestionId, Callable[[StudentId, Score], Score]], /
    ) -> None: ...

    @overload
    def update_score(self, fn: Callable[[StudentId, QuestionId, Score], Score]) -> None: ...

    @overload
    def update_score(self, **kwargs: Callable[[StudentId, Score], Score]) -> None: ...

    def update_score(self, *args: Any, **kwargs: Any) -> None:
        """
        Update the scores for a given question.
        """
        if args and kwargs:
            raise TypeError("update_score() takes either positional or keyword arguments, not both")

        updates: dict[QuestionId, Callable[[StudentId, Score], Score]]
        if kwargs:
            updates = kwargs
        elif len(args) != 1:
            raise TypeError(f"update_score() takes 1 positional argument, got {len(args)}")
        elif callable(args[0]):
            update_fn = cast(Callable[[StudentId, QuestionId, Score], Score], args[0])
            updates = {
                qid: lambda sid, score, qid=qid: update_fn(sid, qid, score)
                for qid in self.quiz.get_question_ids()
            }
        else:
            updates = args[0]

        for student_id, submission in self._grades.items():
            for question_id, response in submission.responses.items():
                if ((fn := updates.get(question_id)) is not None 
                        and not is_disqualification(response.score)):  # fmt: skip
                    response.score = fn(student_id, response.score)

    #
    # Private methods
    #
    def _iter_submissions(self, student_id: StudentId | None) -> _SubmissionsIter:
        if student_id is None:
            return self._grades.items()
        try:
            return [(student_id, self._grades[student_id])]
        except KeyError:
            return []

    def _iter_responses(self, question_id: QuestionId | None, submission: models.SubmissionGrade) -> _ResponsesIter:  # fmt: skip
        if question_id is None:
            return submission.responses.items()
        try:
            return [(question_id, submission.responses[question_id])]
        except KeyError:
            return []


#
# Utilities
#
def collect_validation_errors(errors: list[ValidationError]) -> ValidationError:
    """
    Collect multiple validation errors into a single ValidationError.
    """
    all_errors: list[InitErrorDetails] = []
    for error in errors:
        for err in error.errors(include_context=True):
            student_id = err.get("ctx", {}).get("student_id")
            if student_id is not None:
                err["loc"] = (student_id,) + err["loc"]
            all_errors.append(
                InitErrorDetails(
                    loc=err["loc"],
                    type=err["type"],
                    ctx=err.get("ctx", {}),
                    input=err.get("input"),
                )
            )

    return ValidationError.from_exception_data(
        "Multiple validation errors in submissions", all_errors
    )


def compute_grade(score: Score | Disqualification, value: Decimal) -> Decimal:
    """
    Compute the grade for a given score and question value.

    Args:
        score:
            The score to compute the grade for.
        value:
            The value of the question.
    """
    if isinstance(score, Disqualification):
        return Decimal(0)
    elif isinstance(score, Fraction):
        return chalk_decimal(score.numerator * value / score.denominator)
    return chalk_decimal(score * value)


#
# Persistence
#
def load_grades_from_path(path: Path, quiz: Quiz) -> Grades:
    if not path.suffix == ".csv":
        raise ValueError(f"Expected a CSV file, got {path.suffix}")

    reader = csv.reader(path.open("r"), lineterminator="\n")
    rows = iter(reader)

    # Read header row
    columns = next(rows, None)
    if columns is None:
        return Grades([], quiz)
    n_columns = len(columns)

    if len(columns) < 2 or columns[0] != "id":
        return Grades([], quiz)
    if columns[0] != "id":
        raise ValueError(f"Expected first column to be 'id', got {columns[0]}")

    # Getter functions for the field, start, and end columns
    has_field = len(columns) >= 2 and columns[1] == "field"
    field_idx: int = 1 if has_field else 0

    has_feedback = len(columns) >= 2 + field_idx and columns[1 + field_idx] == "feedback"
    feedback_idx: int = field_idx + (1 if has_feedback else 0)

    question_idx: int = feedback_idx + 1
    question_cols = columns[question_idx:]

    def feedback(row: list[str], /) -> str | None:
        return (row[feedback_idx] if has_feedback else None) or None

    def get_row_type(row: list[str], /) -> Field:
        return (row[field_idx] or "score") if has_field else "score"

    def question_fields(row: list[str], /) -> dict[QuestionId, str | None]:
        return {id: (row[i] or None) for i, id in enumerate(question_cols, start=question_idx)}

    # Populate raw submissions data
    feedbacks: dict[StudentId, str | None] = {}
    submissions: dict[StudentId, dict[QuestionId, dict[Field, str | None]]] = defaultdict(lambda: defaultdict(dict))  # fmt: skip

    student_id = ""
    for i, row in enumerate(reader):
        if len(row) != n_columns:
            raise ValueError(f"Row {i + 1} has {len(row)} columns, expected {n_columns}")

        row_id = row[0]
        if not student_id and not row_id:
            raise ValueError(f"Row {i + 1} has no id")

        row_type = get_row_type(row)
        if row_type == "score":
            student_id = row_id

        responses = submissions[student_id]
        if row_type == "feedback":
            feedbacks[student_id] = feedback(row)

        for qid, answer in question_fields(row).items():
            responses[qid][row_type] = answer

    # Create SubmissionGrade objects validating with Pydantic
    errors: list[ValidationError] = []
    result: dict[StudentId, models.SubmissionGrade] = {}
    for student_id, responses in submissions.items():
        submission = {
            "id": student_id,
            "feedback": feedbacks.get(student_id),
            "responses": {
                qid: obj for qid, obj in responses.items() if obj.get("score") is not None
            },
        }
        try:
            validated = models.SubmissionGrade.model_validate(
                submission,
                context={"quiz": quiz, "student_id": student_id},
            )
        except ValidationError as e:
            errors.append(e)
            raise
        else:
            result[student_id] = validated

    if errors:
        raise collect_validation_errors(errors)

    return Grades(result.values(), quiz)


def save_grades_to_path(
    grades: dict[StudentId, models.SubmissionGrade],
    file: IO[str],
    question_ids: Iterable[QuestionId],
) -> None:
    """
    Save grades to a CSV file at the given path.
    """
    writer = csv.writer(file)

    has_global_feedback = False
    #: Students with a row of each extra field.
    extra: dict[str, set[StudentId]] = {field: set() for field in EXTRA_FIELDS}

    for submission in grades.values():
        if submission.feedback is not None:
            has_global_feedback = True
        for response in submission.responses.values():
            for field, students in extra.items():
                if getattr(response, field) is not None:
                    students.add(submission.id)

    # Create header row
    columns = ["id"]
    has_field = any(extra.values())
    if has_field:
        columns.append("field")
    if has_global_feedback:
        columns.append("feedback")
    columns.extend(question_ids)
    writer.writerow(columns)

    # Write rows for each student
    for student_id, submission in grades.items():
        row = [student_id]
        if has_field:
            row.append("score")
        if has_global_feedback:
            row.append("" if submission.feedback is None else submission.feedback)
        for qid in question_ids:
            response = submission.responses.get(qid)
            row.append(render_score(response.score) if response is not None else "")
        writer.writerow(row)

        # A row of feedback and one of notes, with an empty id
        for field, students in extra.items():
            if student_id not in students:
                continue
            row = ["", field]
            if has_global_feedback:
                row.append("")
            for qid in question_ids:
                response = submission.responses.get(qid)
                value = None if response is None else getattr(response, field)
                row.append("" if value is None else value)
            writer.writerow(row)


def render_score(value: Score | Disqualification) -> str:
    """
    Render a score as a string for CSV output.
    """
    if isinstance(value, Disqualification):
        return str(value)
    elif value == 0:
        return "0.00"
    elif value == 1:
        return "1.00"
    elif isinstance(value, Fraction):
        try:
            return RENDERED_COMMON_FRACTIONS[value]
        except KeyError:
            return f"{value.numerator}/{value.denominator}"
    else:
        return render_decimal(value)
