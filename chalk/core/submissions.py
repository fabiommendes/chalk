from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, overload
from weakref import ref

import opt
from pydantic import ValidationError
from pydantic_core import InitErrorDetails

from ..core.answer import serialize_any_answer
from ..data.protocols import get_id
from ..question import persist_answer, serialize_answer
from ..util import unpack
from . import AnyAnswer, models
from .models import QuestionId, StudentId

if TYPE_CHECKING:
    from ..question import Question
    from .quiz import Quiz
    from .student import Student

log = getLogger(__name__)

type Field = str


class Submissions:
    """
    A collection of submissions for a quiz.
    """

    #
    # Properties
    #
    @property
    def quiz(self) -> Quiz:
        return unpack(self._quiz(), throw=RuntimeError("Quiz reference is dead"))

    #
    # Constructors
    #
    @classmethod
    def load(cls, path: Path, quiz: Quiz) -> Submissions:
        """
        Load Submissions from a tabular format (e.g., CSV, Excel) at the given path.
        """
        return load_submissions_from_csv(path, quiz)

    def __init__(self, submissions: Iterable[models.Submission], quiz: Quiz) -> None:
        self._submissions = {s.id: s for s in submissions}
        self._answers_cache: dict[tuple[StudentId, QuestionId], AnyAnswer | None] = {}
        self._quiz = ref(quiz)

        # Store all questions that have associated responses.
        # A question is considered to have a response if it has an entry in the
        # submissions dictionary and has at least one non-null response in it.
        persisted: set[QuestionId] = set()
        inlined: set[QuestionId] = set()
        for submission in submissions:
            for qid, response in submission.responses.items():
                if qid in persisted or qid in inlined:
                    continue

                question = quiz.get_question(qid)
                response_root = (
                    question
                    and question.get_responses_root()
                    or (self.quiz.root / qid / "responses")
                )
                if response_root.exists():
                    persisted.add(qid)
                else:
                    inlined.add(qid)

        ids = set(self.quiz.get_question_ids())
        if missing := ids - (persisted | inlined):
            msg = ", ".join(sorted(missing))
            msg = f"Questions seen in submissions are not present in quiz {self.quiz.id!r}: {msg}"  # fmt: skip
            log.error(msg)

            inlined.update(missing)

        if extra := (persisted | inlined) - ids:
            msg = ", ".join(sorted(extra))
            msg = f"Answers to questions not found in quiz {self.quiz.id!r}: {msg}"
            log.error(msg)

        self._persisted_questions = frozenset(persisted)
        self._inlined_questions = frozenset(inlined)

    #
    # Getters and setters
    #
    def get_answer(
        self,
        *,
        question: QuestionId | Question,
        student: StudentId | Student,
        inline_only: bool = False,
    ) -> AnyAnswer | None:
        """
        Get the answer for a given question and student.

        Args:
            question:
                The question or question id to get answers for.
            student:
                The student or student id to get answers for.
            inline_only:
                If True, only return answers that were submitted in the
                submissions.csv file. Otherwise search for answers in files.
        """
        question_id = get_id(question)
        student_id = get_id(student)

        # Cache lookup
        try:
            return self._answers_cache[student_id, question_id]
        except KeyError:
            pass

        # Try the response submissions initialized from the "responses.csv" file.
        if question_id in self._inlined_questions:
            try:
                answer = self._submissions[student_id].responses[question_id].answer
            except KeyError:
                answer = None
            self._answers_cache[student_id, question_id] = answer
            return answer

        if inline_only:
            return None

        # Finally, the response might be saved on a separate file under the
        # question directory.
        if (obj := self.quiz.get_question(question_id)) is None:
            raise ValueError(f"Question {question_id} not found in quiz {self.quiz.id}")
        question = obj

        answer = question.get_persisted_answer(student_id)
        self._answers_cache[student_id, question_id] = answer
        return answer

    def set_answer(
        self,
        answer: AnyAnswer | None,
        *,
        question: QuestionId | Question,
        student: StudentId | Student,
        mode: Literal["auto", "inline", "persist"] = "auto",
    ) -> None:
        """
        Set the answer for a given question and student.

        The mode optional parameter controls where the answer is stored.
        * "inline": store the answer inline in the submissions.csv file.
        * "persist": store the answer in a separate file under the question directory.
        * "auto": try to replicate the storage mode of the existing answer.
        """

        question_id = get_id(question)
        student_id = get_id(student)

        # Update the cache
        self._answers_cache[student_id, question_id] = answer

        # Update the submission object
        if student_id not in self._submissions:
            self._submissions[student_id] = models.Submission(id=student_id, responses={})
        submission = self._submissions[student_id]

        #  Determine the storage mode
        if mode == "auto":
            if question_id in self._inlined_questions:
                mode = "inline"
            else:
                mode = "persist"

        if mode == "inline":
            response = submission.responses.setdefault(question_id, models.Response())
            response.answer = answer

        # mode == "persist"
        else:
            if not isinstance(question, Question):
                question = unpack(
                    self.quiz.get_question(question_id),
                    throw=ValueError(f"Question {question_id} not found in quiz {self.quiz.id}"),
                )
            persist_answer(question, student_id, answer, error="raise", overwrite=True)

    #
    # Iteration
    #
    @overload
    def iter_answers(
        self, *, question: QuestionId | Question
    ) -> Iterable[tuple[StudentId, AnyAnswer]]: ...

    @overload
    def iter_answers(
        self, *, student: StudentId | Student
    ) -> Iterable[tuple[QuestionId, AnyAnswer]]: ...

    def iter_answers(
        self,
        *,
        question: QuestionId | Question | None = None,
        student: StudentId | Student | None = None,
    ) -> Iterable[tuple[Any, AnyAnswer]]:
        """
        Iterate over all answers for a given question.
        """
        if question is None and student is None:
            raise TypeError("Must specify either question or student")
        if question is not None and student is not None:
            raise TypeError("Cannot specify both question and student")

        answers: Iterable[Any] = []
        if question is not None:
            answers = self._iter_answers_for_question(get_id(question))

        if student is not None:
            answers = self._iter_answers_for_student(get_id(student))

        for id, answer in answers:
            if answer is not None:
                yield id, answer

    def _iter_answers_for_question(
        self, question_id: QuestionId
    ) -> Iterable[tuple[StudentId, AnyAnswer | None]]:
        """
        Iterate over all answers for a given question.
        """
        for student_id, submission in self._submissions.items():
            yield (student_id, self.get_answer(question=question_id, student=student_id))

    def _iter_answers_for_student(
        self, student_id: StudentId
    ) -> Iterable[tuple[QuestionId, AnyAnswer | None]]:
        """
        Iterate over all answers for a given student.
        """
        questions = self.quiz.get_question_ids()
        for question_id in questions:
            yield (question_id, self.get_answer(question=question_id, student=student_id))

    def iter_submissions(self) -> Iterable[Submission]:
        """
        Iterate over all submissions.
        """
        persisted = self.persisted_questions()
        for student_id, submission in self._submissions.items():
            responses = {
                qid: Response(
                    answer=self.get_answer(question=qid, student=student_id),
                    start=response.start,
                    end=response.end,
                )
                for qid, response in submission.responses.items()
            }
            for id in persisted - submission.responses.keys():
                responses[id] = Response(
                    answer=self.get_answer(question=id, student=student_id),
                    start=None,
                    end=None,
                )
            yield Submission(
                id=submission.id,
                start=submission.start,
                end=submission.end,
                responses=responses,
            )

    #
    # Persistence and transformations
    #
    def reload(self) -> None:
        """
        Reload submission object.
        """
        new = Submissions.load(self.quiz.root / "submissions.csv", self.quiz)
        self.__dict__.update(new.__dict__)

    def save(self, *, path: Path | None = None, inline_only: bool = False) -> None:
        """
        Save the submissions to a local file.
        """
        if path is None:
            path = self.quiz.root / "submissions.csv"
        if path.suffix != ".csv":
            raise ValueError(f"Expected a CSV file, got {path.suffix}")

        questions = [*self.quiz.get_question_ids()]

        # Prepare submissions
        submissions: dict[StudentId, models.Submission] = {}
        for student_id, submission in self._submissions.items():
            new = submission.model_copy()
            responses = new.responses = {}

            for question_id, response in submission.responses.items():
                responses[question_id] = response.model_copy()
                if question_id in self._persisted_questions:
                    responses[question_id].answer = None

            submissions[student_id] = new

        save_submissions_to_csv(submissions, path, questions=questions)

        # We update the submissions files to update any possible changes in
        # the answers cache.
        errors: list[Exception] = []
        if inline_only:
            return

        for (student_id, question_id), answer in self._answers_cache.items():
            if answer is None or question_id not in self._persisted_questions:
                continue

            question = self.quiz.get_question(question_id)
            if question is None:
                error = ValueError(f"Question {question_id} not found in quiz {self.quiz.id}")
                errors.append(error)
                continue

            if answer is not None:
                try:
                    persist_answer(question, student_id, answer, error="raise", overwrite=True)
                except ValueError as e:
                    errors.append(e)

        if errors:
            raise ValueError("Failed to persist some answers", errors)

    def update_submissions(
        self,
        fn: Callable[[StudentId, models.Submission], models.Submission | None],
        /,
        *,
        dry_run: bool = False,
    ) -> None:
        """
        Update submissions for all submissions using the given updater function.

        Args:
            updater:
                A function that takes a submission and returns a new submission.
                If the function returns None, the submission is removed.

                The updater function may modify the submission in place or
                return a new submission object.
            dry_run:
                If True, do not persist any changes to the filesystem. This can
                lead to inconsistencies for questions that are persisted in
                separate files instead of the submissions.csv file. Use with caution.
        """
        seen_answers: set[tuple[StudentId, QuestionId]] = set()
        persisted_questions = self.persisted_questions()

        for student_id, old_submission in list(self._submissions.items()):
            submission = old_submission.model_copy(deep=True)
            self._hydrate_submission(student_id, old_submission, seen_answers.add)

            match fn(student_id, submission):
                case None:
                    del self._submissions[student_id]

                    # Remove persisted files
                    if not dry_run:
                        for qid in persisted_questions & old_submission.responses.keys():
                            remove_persisted_question(student_id, qid, self.quiz)

                    # Remove answers from cache
                    for sid, qid in list(self._answers_cache):
                        if sid == student_id:
                            del self._answers_cache[(sid, qid)]

                case submission:
                    self._submissions[student_id] = submission

                    # Update cache and persisted answers
                    for question_id, response in submission.responses.items():
                        loc = (student_id, question_id)
                        seen_answers.add(loc)
                        self._answers_cache[loc] = response.answer

                        if question_id in persisted_questions and not dry_run:
                            update_persisted_question(
                                student_id=student_id,
                                question_id=question_id,
                                answer=response.answer,
                                quiz=self.quiz,
                            )

        if not dry_run:
            self.save()

        assert not (self._answers_cache.keys() - seen_answers), (
            "Some answers in the cache were not seen during the update."
        )

    def update_responses(
        self,
        question: Question | QuestionId,
        fn: Callable[[StudentId, models.Response], models.Response | None],
        /,
        *,
        dry_run: bool = False,
    ) -> None:
        """
        Update responses for all submissions using the given updater function.

        Args:
            updater:
                A function that takes a response and returns a new response.
                If the function returns None, the response is removed.
        """
        question_id = get_id(question)
        is_persisted = question_id in self.persisted_questions()

        for student_id, submission in list(self._submissions.items()):
            old_response = submission.responses.get(question_id)
            if old_response is None:
                continue

            response = old_response.model_copy(deep=True)
            self._hydrate_response(student_id, question_id, old_response, is_persisted=is_persisted)

            match fn(student_id, response):
                case None:
                    submission.responses.pop(question_id, None)

                    # Remove persisted files and cache
                    self._answers_cache.pop((student_id, question_id), None)
                    if not dry_run and is_persisted:
                        remove_persisted_question(student_id, question_id, self.quiz)

                case response:
                    submission.responses[question_id] = response

                    # Update cache and persisted answers
                    self._answers_cache[(student_id, question_id)] = response.answer

                    if is_persisted and not dry_run:
                        update_persisted_question(
                            student_id=student_id,
                            question_id=question_id,
                            answer=response.answer,
                            quiz=self.quiz,
                        )

        if not dry_run:
            self.save()

    def inline(self, question: Question | QuestionId, /) -> None:
        """
        Inline answers that are stored in separate files back into the
        submissions.csv file.

        It is a NO-OP if answers are already inlined.
        """

        question_id = get_id(question)
        question = self._as_question(question)
        root = question.get_responses_root()
        suffix = question.get_answer_suffix()

        if not root.exists():
            return

        remove_files: list[Path] = []
        saved: dict[StudentId, AnyAnswer] = {}
        for file in root.iterdir():
            if not (file.is_file() and file.suffix == suffix):
                continue

            student_id = file.stem
            answer = file.read_text()
            remove_files.append(file)
            saved[student_id] = answer
            try:
                self._answers_cache[(student_id, question_id)] = question.validate_answer(answer)
            except ValueError:
                pass

        # Update inlined/persisted questions sets
        inlined = set(self._inlined_questions)
        persisted = set(self._persisted_questions)
        inlined.add(question_id)
        persisted.discard(question_id)

        self._inlined_questions = frozenset(inlined)
        self._persisted_questions = frozenset(persisted)

        for student_id, answer in saved.items():
            sub = self._submissions.setdefault(student_id, models.Submission(id=student_id))
            response = sub.responses.setdefault(question_id, models.Response())
            response.answer = answer

        self.save(inline_only=True)

        for file in remove_files:
            try:
                file.unlink()
            except OSError as e:
                log.warning(f"Error removing persisted file for {question.id!r}: {e}")

        # Try remove empty directories
        try:
            root.rmdir()
        except OSError:
            log.info(f"Non-empty responses dir: {question.id!r}")
        try:
            root.parent.rmdir()
        except OSError:
            pass

    def extract(self, question: Question | QuestionId, *, force: bool = False) -> None:
        """
        Move answers that are stored inline in the submissions.csv file
        into separate files under the question directory.

        It is a NO-OP if answers are already stored in separated files.
        """
        question_id = get_id(question)
        question = self._as_question(question)
        root = question.get_responses_root(mkdir=True)
        suffix = question.get_answer_suffix()

        def get_sub(id: StudentId) -> models.Submission:
            return self._submissions.setdefault(id, models.Submission(id=id, responses={}))

        for student_id, answer in self.iter_answers(question=question_id):
            if answer is None:
                continue

            file = root / f"{student_id}{suffix}"
            if force or not file.exists():
                file.write_text(serialize_answer(question, answer, error="ignore"))
                submission = get_sub(student_id)
                response = submission.responses.setdefault(question_id, models.Response())
                response.answer = None
            else:
                msg = f"File already exists for {question.id!r} and student {student_id!r}: {file}"
                log.warning(msg)

        # Update inlined/persisted questions sets
        inlined = set(self._inlined_questions)
        persisted = set(self._persisted_questions)
        persisted.add(question_id)
        inlined.discard(question_id)

        self._inlined_questions = frozenset(inlined)
        self._persisted_questions = frozenset(persisted)

    def inlined_questions(self) -> frozenset[QuestionId]:
        """
        The set of questions whose answers are stored inline in the spreadsheet
        file.
        """
        return self._inlined_questions

    def persisted_questions(self) -> frozenset[QuestionId]:
        """
        The set of questions whose answers are not stored inline in the spreadsheet
        file
        """
        return self._persisted_questions

    def _hydrate_submission(
        self,
        student_id: StudentId,
        submission: models.Submission,
        /,
        on_visit: Callable[[tuple[StudentId, QuestionId]], Any] = lambda _: None,
    ) -> None:
        """
        Hydrate submission with answers from the cache or persisted files.
        """

        persisted = self.persisted_questions()
        for question_id, response in submission.responses.items():
            loc = (student_id, question_id)
            is_persisted = question_id in persisted
            self._hydrate_response(student_id, question_id, response, is_persisted=is_persisted)
            on_visit(loc)

    def _hydrate_response(
        self,
        student_id: StudentId,
        question_id: QuestionId,
        response: models.Response,
        is_persisted: bool | None = None,
    ) -> None:
        """
        Hydrate a single response with an answer from the cache or persisted files.
        """
        if is_persisted is None:
            is_persisted = question_id not in self.persisted_questions()

        # Try to load from cache or file
        try:
            response.answer = self._answers_cache[(student_id, question_id)]
        except KeyError:
            pass
        else:
            return

        if is_persisted:
            response.answer = self.get_answer(question=question_id, student=student_id)

    def _as_question(self, question: Question | QuestionId) -> Question:
        """
        Convert a question id to a Question object.
        """
        if isinstance(question, QuestionId):
            question = unpack(
                self.quiz.get_question(question),
                throw=ValueError(f"Question {question} not found in quiz {self.quiz.id}"),
            )
        return question


#
# Auxiliary types
#
class Submission(NamedTuple):
    id: StudentId
    start: datetime | None
    end: datetime | None
    responses: dict[QuestionId, Response]


class Response(NamedTuple):
    answer: AnyAnswer | None
    start: datetime | None
    end: datetime | None


#
# Auxiliary functions
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


#
# Persistence and validation
#
def load_submissions_from_csv(
    path: Path,
    quiz: Quiz,
    error: Literal["raise", "ignore", "warn"] = "warn",
) -> Submissions:

    if not path.suffix == ".csv":
        raise ValueError(f"Expected a CSV file, got {path.suffix}")

    reader = csv.reader(path.open("r"), lineterminator="\n")
    rows = iter(reader)

    columns = next(rows, None)
    if columns is None:
        raise ValueError(f"Empty file: {path}")
    n_columns = len(columns)

    # Empty table
    if len(columns) < 2 or columns[0] != "id":
        return Submissions([], quiz)

    if columns[0] != "id":
        raise ValueError(f"Expected first column to be 'id', got {columns[0]}")

    # Getter functions for the field, start, and end columns
    has_field = len(columns) >= 2 and columns[1] == "field"
    field_idx: int = 1 if has_field else 0

    has_start = len(columns) >= 2 + field_idx and columns[1 + field_idx] == "start"
    start_idx: int = field_idx + (1 if has_start else 0)

    has_end = len(columns) >= 2 + start_idx and columns[1 + start_idx] == "end"
    end_idx: int = start_idx + (1 if has_end else 0)
    question_idx: int = end_idx + 1
    question_cols = columns[question_idx:]

    def start(row: list[str], /) -> str | None:
        return (row[start_idx] if has_start else None) or None

    def end(row: list[str], /) -> str | None:
        return (row[end_idx] if has_end else None) or None

    def get_field(row: list[str], /) -> Field:
        return (row[field_idx] or "answer") if has_field else "answer"

    def question_fields(row: list[str], /) -> dict[QuestionId, str | None]:
        return {id: (row[i] or None) for i, id in enumerate(question_cols, start=question_idx)}

    # Populate raw submissions data
    starts: dict[StudentId, str | None] = {}
    ends: dict[StudentId, str | None] = {}
    submissions: dict[StudentId, dict[QuestionId, dict[Field, str | None]]] = defaultdict(lambda: defaultdict(dict))  # fmt: skip

    student_id = ""
    for i, row in enumerate(reader):
        if len(row) != n_columns:
            raise ValueError(f"Row {i + 1} has {len(row)} columns, expected {n_columns}")

        row_id = row[0]
        if not student_id and not row_id:
            raise ValueError(f"Row {i + 1} has no id")

        field = get_field(row)
        if field == "answer":
            student_id = row_id

        responses = submissions[student_id]
        if field == "answer":
            starts[student_id] = start(row)
            ends[student_id] = end(row)

        for qid, answer in question_fields(row).items():
            responses[qid][field] = answer

    # Create Submission objects validating with Pydantic
    errors: list[ValidationError] = []
    result: dict[StudentId, models.Submission] = {}
    for student_id, responses in submissions.items():
        submission = {
            "id": student_id,
            "start": starts.get(student_id),
            "end": ends.get(student_id),
            "responses": {k: v for k, v in responses.items() if v},
        }
        try:
            validated = models.Submission.model_validate(
                submission,
                context={"quiz": quiz, "student_id": student_id},
            )
        except ValidationError as e:
            errors.append(e)
        else:
            result[student_id] = validated

    if errors and error == "raise":
        raise collect_validation_errors(errors)
    if errors and error == "warn":
        for e in errors:
            print(e)

    return Submissions(result.values(), quiz)


def save_submissions_to_csv(
    submissions: dict[StudentId, models.Submission],
    path: Path,
    questions: list[QuestionId],
) -> None:
    """
    Save the submissions to a CSV file at the given path.
    """

    has_start_col = False
    has_end_col = False
    has_start: dict[QuestionId, bool] = defaultdict(bool)
    has_end: dict[QuestionId, bool] = defaultdict(bool)
    students: list[StudentId] = []

    for submission in submissions.values():
        students.append(submission.id)
        has_start_col = has_start_col or submission.start is not None
        has_end_col = has_end_col or submission.end is not None
        for qid, response in submission.responses.items():
            if response.start is not None:
                has_start[qid] = True
            if response.end is not None:
                has_end[qid] = True

    # Build the header row
    columns = ["id"]
    if has_start_col:
        columns.append("start")
    if has_end_col:
        columns.append("end")
    columns.extend(questions)

    fd = io.StringIO(newline="")
    writer = csv.writer(fd, lineterminator="\n")
    writer.writerow(columns)

    for student_id in students:
        submission = submissions[student_id]
        base_row: list[str] = [submission.id]
        answer_row: list[str] = [submission.id]
        if has_start_col:
            answer_row.append(opt.map(datetime.isoformat, submission.start) or "")
            base_row.append("")
        if has_end_col:
            answer_row.append(opt.map(datetime.isoformat, submission.end) or "")
            base_row.append("")

        # Write answers
        row = answer_row
        for qid in questions:
            response = submission.responses.get(qid)
            row.append(serialize_any_answer(opt.getattr(response, "answer")))
        writer.writerow(row)

        # Write start and end times for each question
        if has_start:
            row = base_row[:]
            for qid in questions:
                response = submission.responses.get(qid)
                row.append(opt.map(datetime.isoformat, opt.getattr(response, "start")) or "")
            writer.writerow(row)

        if has_end:
            row = base_row[:]
            for qid in questions:
                response = submission.responses.get(qid)
                row.append(opt.map(datetime.isoformat, opt.getattr(response, "end")) or "")
            writer.writerow(row)

    path.write_text(fd.getvalue())


def remove_persisted_question(student_id: StudentId, question_id: QuestionId, quiz: Quiz):
    question = quiz.get_question(question_id)

    if question is not None:
        ext = question.get_answer_extension() or "txt"
        path = question.root / f"{student_id}.{ext}"
        if path.exists():
            path.unlink()
        return

    # Question do not exist (maybe it was deleted from the quiz)
    paths = [*(quiz.root / question_id).glob(f"{student_id}.*")]
    match paths:
        case []:
            return
        case [path]:
            path.unlink()
        case _:
            for path in paths:
                path.unlink()


def update_persisted_question(
    student_id: StudentId, question_id: QuestionId, answer: AnyAnswer | None, quiz: Quiz
):
    if answer is None:
        remove_persisted_question(student_id, question_id, quiz)
        return

    question = quiz.get_question(question_id)
    if question is not None:
        persist_answer(question, student_id, answer, error="ignore", overwrite=True)
        return

    # Question do not exist (maybe it was deleted from the quiz)
    remove_persisted_question(student_id, question_id, quiz)
    path = quiz.root / question_id / f"{student_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_any_answer(answer))
