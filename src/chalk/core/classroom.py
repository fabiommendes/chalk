from __future__ import annotations

import locale
import tomllib
from decimal import Decimal
from functools import cached_property
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Literal, NamedTuple, overload

import opt
import pandas as pd
from natsort import natsorted
from rich.prompt import Prompt

from ..data import load_spreadsheet, load_structured_data
from ..question import Question
from . import models
from .decimal import set_decimal_precision
from .error import ChalkError, ChalkException, RosterNotFoundError
from .models import Autograder, QuestionId, QuizId, StudentId
from .quiz import Quiz
from .roster import Roster
from .student import Student
from .submissions import Submissions

if TYPE_CHECKING:
    from .quiz import Quiz

log = getLogger(__name__)

NO_GRADE = None
SPREADSHEET_EXTENSIONS = {".csv", ".xlsx"}
STRUCTURED_DATA_EXTENSIONS = {".json", ".yaml", ".yml"}
RESERVED_NON_QUIZ_NAMES = {
    "template",
    "autograde",
}


class Classroom:
    """
    A classroom object.

    The entry point to access all other Chalk objects, including students,
    quizzes, and grades.
    """

    #
    # Properties
    #
    @property
    def autograder(self) -> Autograder:
        return self._conf.autograder or Autograder()

    @property
    def name(self) -> str:
        return self._conf.name

    @property
    def teacher(self) -> str:
        return self._conf.teacher

    @property
    def lang(self) -> str:
        return self._conf.lang or locale.getdefaultlocale()[0] or "C"

    @property
    def root(self) -> Path:
        return self._root

    @property
    def roster(self) -> Roster:
        return self.get_roster(on_empty="create")

    #
    # Constructors
    #
    @classmethod
    def load(cls, root: Path | None = None) -> Classroom:
        """
        Load a classroom from the given root directory.
        """
        root = root or find_project_root()
        if root is None:
            raise RuntimeError("Could not find the project root")

        with (root / "chalk.toml").open("rb") as fd:
            data = tomllib.load(fd)["chalk"]
            data["name"] = data.pop("classroom")

        conf = models.Classroom.model_validate(data)

        # Set global precision
        set_decimal_precision(conf.decimal_places)
        return cls(root, conf)

    @overload
    @classmethod
    def from_prompt(
        cls,
        root: Path | None = None,
        *,
        quiz_id: str | None,
        on_error: Callable[[str], Exception] | None = None,
    ) -> ClsQuiz: ...

    @overload
    @classmethod
    def from_prompt(
        cls,
        root: Path | None = None,
        *,
        quiz_id: str | None = None,
        question_id: str | None,
        on_error: Callable[[str], Exception] | None = None,
    ) -> ClsQuizQuestion: ...

    @overload
    @classmethod
    def from_prompt(
        cls,
        root: Path | None = None,
        *,
        quiz_id: str | None = None,
        question_id: str | None,
        submissions: Literal[True],
        on_error: Callable[[str], Exception] | None = None,
    ) -> ClsQuizQuestion: ...

    @classmethod
    def from_prompt(cls, root: Path | None = None, **kwargs: Any) -> Any:
        """
        Prompt the user to select a classroom root directory and load it.
        """
        cfg = cls.load(root)

        quiz = None
        if "quiz_id" in kwargs:
            quiz = cfg.prompt_quiz(kwargs["quiz_id"])

        question = None
        if "question_id" in kwargs:
            question = cfg.prompt_question(quiz, kwargs["question_id"])

        if quiz is not None and question is not None:
            return ClsQuizQuestion(cfg, quiz, question)
        if quiz is not None:
            return ClsQuiz(cfg, quiz)
        raise TypeError("Must provide at least quiz_id or question_id")

    def __init__(self, root: Path, conf: models.Classroom) -> None:
        self._root = root
        self._conf = conf
        self._quiz_cache: dict[QuizId, Quiz] = {}

    #
    # Lazy loading
    #
    @cached_property
    def _roster(self) -> Roster:
        path = self._root / "roster.csv"
        if not path.exists():
            raise RosterNotFoundError()

        table = load_spreadsheet(path)
        raw = table.to_dicts()
        return Roster.from_json(raw, path=path, classroom=self)

    #
    # Getters/setters
    #
    def get_roster(self, on_empty: Literal["raise", "create"] = "create") -> Roster:
        """
        Read the roster file at the given path and return a Roster object.

        Args:
            on_empty: What to do if the roster file is not found. Options are "raise" to raise an error or "create" to create a new Roster object.
        """
        try:
            return self._roster
        except RosterNotFoundError:
            if on_empty == "create":
                return Roster(path=self._root / "roster.csv", data={})
            raise

    def get_student(self, student_id: StudentId) -> Student | None:
        """
        Get a student by their ID.
        """
        return self.get_roster().get(student_id)

    def get_quiz(self, quiz_id: str) -> Quiz | None:
        """
        Get a quiz by its ID.
        """
        if quiz_id in self._quiz_cache:
            return self._quiz_cache[quiz_id]

        conf_path = self.root / quiz_id / "conf.yaml"
        if not conf_path.exists():
            return None

        try:
            conf_data = load_structured_data(conf_path)
        except ValueError:
            msg = f"Invalid quiz config: {conf_path.relative_to(self.root)}"
            raise ChalkError.INVALID_RESOURCE(msg)

        conf = models.Quiz.model_validate(conf_data, context={"quiz": quiz_id})
        quiz = Quiz(quiz_id, conf, classroom=self)
        self._quiz_cache[quiz_id] = quiz
        return quiz

    def get_grades(self, total: bool = True) -> pd.DataFrame:
        """
        Get a table of grades for all students in the classroom.
        """
        columns: dict[QuizId, pd.Series] = {}
        weights: dict[QuizId, Decimal] = {}

        for quiz in self.iter_quizzes():
            df = quiz.grades.get_dataframe(total="__total__")
            columns[quiz.id] = df["__total__"]
            if total:
                weights[quiz.id] = opt.unwrap(quiz.weight, Decimal(0))

        if total:
            total_weights = sum(weights.values())
            weights = {k: v / total_weights for k, v in weights.items()}
            parts = {k: columns[k] * weights[k] for k in columns}  # type: ignore

            columns["total"] = pd.DataFrame(parts).sum(axis=1)

        return pd.DataFrame(columns)

    #
    # Interactive/prompting methods
    #
    def prompt_quiz(self, quiz_id: str | None) -> Quiz:
        if quiz_id is not None:
            return opt.unpack(
                self.get_quiz(quiz_id),
                throw=ChalkError.RESOURCE_NOT_FOUND(f"No quiz {quiz_id!r} found"),
            )

        quizzes = {q.id: q for q in self.iter_quizzes()}

        if len(quizzes) == 1:
            return quizzes.popitem()[1]

        quiz_id = Prompt.ask("Quiz", choices=list(quizzes))
        if quiz_id not in quizzes:
            raise ChalkError.RESOURCE_NOT_FOUND(f"No quiz {quiz_id!r} found")
        return quizzes[quiz_id]

    def prompt_question(
        self,
        quiz: QuizId | Quiz | None = None,
        question_id: QuestionId | None = None,
    ) -> Question:
        """
        Prompt the user to select a question from a quiz.
        """
        if isinstance(quiz, Quiz):
            quiz = quiz.id
        quiz = self.prompt_quiz(quiz)

        if question_id is None:
            question_ids = quiz.get_questions()
            question_id = Prompt.ask("Question", choices=list(question_ids))

        question = quiz.get_question(question_id)
        if question is None:
            msg = f"No question {question_id!r} found in quiz {quiz.id!r}"
            raise ChalkError.RESOURCE_NOT_FOUND(msg)
        return question

    def prompt_student(self, student_id: StudentId | None = None, fuzzy: bool = False) -> Student:
        """
        Prompt the user to select a student from the roster.
        """

        interactive = student_id is None
        roster = self.get_roster(on_empty="raise")
        student: Student | None = None

        if student_id is not None:
            student = roster.get(student_id)
            if student is None and not fuzzy:
                raise ChalkError.RESOURCE_NOT_FOUND(f"No student {student_id!r} found")
        else:
            student_id = Prompt.ask("Student ID")

        if student is None:
            student = roster.get(student_id)
        if fuzzy and student is None:
            students = roster.fuzzy_get(student_id)
            if interactive and len(students) > 1:
                student_id = Prompt.ask(
                    "Multiple students found. Please select one",
                    choices=[s.id for s in students],
                )
                student = roster.get(student_id)
            student = students[0] if students else None
        if student is None:
            raise ChalkError.RESOURCE_NOT_FOUND(f"No student {student_id!r} found")
        return student

    #
    # Iterators
    #
    def iter_students(self) -> Iterable[Student]:
        """
        Iterate over the students in the classroom.
        """
        yield from self.get_roster().values()

    def iter_quizzes(self) -> Iterable[Quiz]:
        """
        Iterate over all quizzes in the classroom.
        """
        for subdir in natsorted(self.root.iterdir(), key=lambda p: p.name):
            if not subdir.is_dir():
                continue

            if subdir.name in RESERVED_NON_QUIZ_NAMES:
                continue

            try:
                quiz = self.get_quiz(subdir.name)
            except ChalkException as e:
                log.warning(f"Error loading quiz {subdir.name}: {e}")
                continue

            if quiz is not None:
                yield quiz


#
# Utility functions
#
def find_project_root(path: Path | None = None) -> Path | None:
    """
    Locate the root of the Chalk project by looking for the chalk.toml configuration
    or the roster file.

    Raises RuntimeError if no suitable root is found.
    """

    if path is None:
        path = Path.cwd()

    while path:
        if is_project_root(path):
            return path
        parent = path.parent
        if parent == path:
            break
        path = parent

    return None


def is_project_root(path: Path) -> bool:
    """
    Check if path is a project root.
    """
    if not path.is_dir():
        return False

    if (path / "chalk.toml").exists():
        return True

    for p in path.glob("roster.*"):
        if p.suffix in SPREADSHEET_EXTENSIONS:
            return True

    return False


#
# Cursor types - return classroom objects with extra data
#
class ClsQuiz(NamedTuple):
    classroom: Classroom
    quiz: Quiz


class ClsQuizQuestion(NamedTuple):
    classroom: Classroom
    quiz: Quiz
    question: Question


class ClsQuizSubQuestion(NamedTuple):
    classroom: Classroom
    quiz: Quiz
    submissions: Submissions
    question: Question


class ClsQuizSub(NamedTuple):
    classroom: Classroom
    quiz: Quiz
    submissions: Submissions
