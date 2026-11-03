from __future__ import annotations

import csv
import locale
import tomllib
from collections.abc import Callable, Iterable
from decimal import Decimal
from functools import cached_property
from logging import getLogger
from pathlib import Path
from types import ModuleType
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    NamedTuple,
    Never,
    cast,
    overload,
)

import opt
import pandas as pd
from natsort import natsorted
from rich.prompt import Prompt

from ..data import load_structured_data
from ..numeric import to_decimal
from ..question import Question
from ..util import unpack
from . import models
from .decimal import set_decimal_precision
from .error import ChalkError, ChalkException, ResourceNotFoundError, RosterNotFoundError
from .models import Autograder, QuestionId, QuizId, StudentId
from .quiz import Quiz
from .roster import DEFAULT_ID_COLUMN, Roster
from .student import Student
from .submissions import Submissions

if TYPE_CHECKING:
    from .quiz import Quiz

log = getLogger(__name__)

NO_GRADE = None
SPREADSHEET_EXTENSIONS = {".csv"}
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
    def profiles(self) -> dict[str, dict[str, Any]]:
        """
        The [profiles] tables of chalk.toml, as written.
        """
        return self._conf.profiles

    @property
    def name(self) -> str:
        return self._conf.name

    @property
    def teacher(self) -> str:
        return self._conf.teacher

    @property
    def lang(self) -> str:
        return self._conf.lang or locale.getlocale()[0] or "C"

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
            toml = tomllib.load(fd)
            data = toml["chalk"]
            data["name"] = data.pop("classroom")
            data["profiles"] = toml.get("profiles", {})

        conf = models.Classroom.model_validate(data)

        # Set global precision
        set_decimal_precision(conf.decimal_places)
        return cls(root, conf)

    @overload
    @classmethod
    def from_prompt(
        cls,
        *,
        root: Path | None = None,
        quiz_id: str | None,
        on_error: Callable[[str], Exception] | None = None,
    ) -> ClsQuiz: ...

    @overload
    @classmethod
    def from_prompt(
        cls,
        *,
        root: Path | None = None,
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

    @overload
    @classmethod
    def from_prompt(
        cls,
        loc: str | None = None,
        *,
        root: Path | None = None,
        on_error: Callable[[str], Exception] | None = None,
        check_exist: Literal[False] = False,
    ) -> OptClsQuizQuestion: ...

    @overload
    @classmethod
    def from_prompt(
        cls,
        loc: str | None = None,
        *,
        root: Path | None = None,
        on_error: Callable[[str], Exception] | None = None,
        check_exist: Literal[True],
    ) -> ClsQuizQuestion: ...

    @classmethod
    def from_prompt(cls, *args, check_exist=False, **kwargs: Any) -> Any:
        """
        Prompt the user to select a classroom root directory and load it.
        """
        cfg = cls.load(kwargs.pop("root", None))
        if len(args) > 1:
            msg = f"from_prompt() takes at most 1 positional argument but {len(args)} were given"
            raise TypeError(msg)

        # Fetch from a loc like a quiz_id, quiz_id/question_id
        if args:
            expect_question = False
            loc = cast(str, args[0])
            if loc is None:
                return OptClsQuizQuestion(cfg, None, None)

            if "/" in loc:
                quiz_id, question_id = loc.split("/", 1)
                expect_question = check_exist
            else:
                quiz_id, question_id = loc, None

            quiz = cfg.get_quiz(quiz_id)

            question = None
            if question_id is not None and quiz is not None:
                question = quiz.get_question(question_id)
                if question is None:
                    raise ResourceNotFoundError(
                        f"Question {question_id!r} does not exist in quiz {quiz_id!r}!",
                        "question",
                        question_id,
                    )

            if check_exist and quiz is None:
                raise ResourceNotFoundError(f"Quiz {quiz_id!r} does not exist!", "quiz", quiz_id)
            if expect_question and question is None:
                raise ResourceNotFoundError(f"Quiz {quiz_id!r} does not exist!", "quiz", quiz_id)

            return OptClsQuizQuestion(cfg, quiz, question)

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

        with path.open(newline="", encoding="utf-8") as fd:
            raw = [
                {k: v or None for k, v in row.items() if k is not None}
                for row in csv.DictReader(fd)
            ]
        return Roster.from_json(raw, path=path, classroom=self, id_column=self._conf.student_id)

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
                return Roster(
                    path=self._root / "roster.csv",
                    data={},
                    id_column=self._conf.student_id or DEFAULT_ID_COLUMN,
                )
            raise

    def get_student(self, student_id: StudentId, fuzzy: bool = False) -> Student | None:
        """
        Get a student by their ID.
        """
        if fuzzy:
            return opt.single(self.get_roster().get_fuzzy(student_id, max_matches=1))
        return self.get_roster().get(student_id)

    def get_quiz(self, quiz_id: str) -> Quiz | None:
        """
        Get a quiz by its ID.
        """
        if quiz_id in self._quiz_cache:
            return self._quiz_cache[quiz_id]

        quiz_ids = set(self.iter_quiz_ids())
        if quiz_id not in quiz_ids:
            quiz_ids_no_case = {q.casefold(): q for q in quiz_ids}
            if quiz_id.casefold() in quiz_ids_no_case:
                quiz_id = quiz_ids_no_case[quiz_id.casefold()]
            else:
                return

        conf_path = self.root / quiz_id / "conf.yaml"
        try:
            conf_data = load_structured_data(conf_path)
        except ValueError:
            msg = f"Invalid quiz config: {conf_path.relative_to(self.root)}"
            raise ChalkError.INVALID_RESOURCE(msg)

        conf = models.Quiz.model_validate(
            conf_data,
            context={"quiz": quiz_id, "path": conf_path},
            extra="forbid",
        )
        quiz = Quiz(quiz_id, conf, classroom=self)
        self._quiz_cache[quiz_id] = quiz
        return quiz

    def get_grades(self, total: bool = True, final: bool | None = None) -> pd.DataFrame:
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

        df = pd.DataFrame(columns)
        if final is False:
            return df

        grader = self.get_final_grader()
        if final is None and grader is None:
            return df

        if grader is None:
            weights = {q.id: q.weight for q in self.iter_quizzes()}
            total_weights = sum(weights.values())
            weights = {k: v / total_weights for k, v in weights.items()}
            grader = lambda grades: sum(grades[q] * weights[q] for q in grades)

        clean = lambda d: d
        if total:
            clean = lambda d: {k: v for k, v in d.items() if k != "total"}

        fn = lambda row: grader(clean(row.to_dict()))
        df["final"] = df.fillna(cast(Any, Decimal(0))).apply(fn, axis=1)

        return df

    def get_final_grader(
        self,
    ) -> Callable[[dict[QuestionId, Decimal | None]], Decimal | str] | None:
        """
        Return a function that receives a mapping from question IDs to grades
        and returns a final grade for the student.

        The grades can be numeric (Decimal) or a string (e.g., "Incomplete", "A", "B+", etc).
        """
        mod = self.get_conf_module()
        if mod is not None and hasattr(mod, "final_grade"):
            return wrap_final_grader(mod.final_grade)
        return None

    def get_conf_module(self) -> ModuleType | None:
        """
        Return the configuration module for the classroom, if available.

        This is a file named conf.py that contains some special python functions
        that can be used to customize how chalk behaves.
        """
        for path in [self.root / "conf.py", self.root / "scripts" / "conf.py"]:
            if path.exists():
                import importlib.util

                spec = importlib.util.spec_from_file_location("conf", path)
                if spec is None or spec.loader is None:
                    return None
                mod = importlib.util.module_from_spec(spec)

                try:
                    spec.loader.exec_module(mod)
                except Exception as e:
                    log.error(f"Error loading {path}: {e}")
                    pass
                return mod
        return None

    #
    # Interactive/prompting methods
    #
    def prompt_quiz(self, quiz_id: str | None) -> Quiz:
        if quiz_id is not None:
            return unpack(
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
            students = roster.get_fuzzy(student_id)
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
        for id in self.iter_quiz_ids():
            try:
                quiz = self.get_quiz(id)
            except ChalkException as e:
                log.warning(f"Error loading quiz {id}: {e}")
                continue

            if quiz is not None:
                yield quiz

    def iter_quiz_ids(self) -> Iterable[QuizId]:
        """
        Iterate over all quiz IDs in the classroom.
        """
        for subdir in natsorted(self.root.iterdir(), key=lambda p: p.name):
            if not subdir.is_dir():
                continue

            if subdir.name in RESERVED_NON_QUIZ_NAMES:
                continue

            conf_path = subdir / "conf.yaml"
            if conf_path.exists():
                yield subdir.name


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


def wrap_final_grader(
    func: Callable[..., Decimal | str],
) -> Callable[[dict[QuestionId, Decimal | None]], Decimal | str]:
    """
    Wrap a final grader function to ensure it returns a Decimal or str.
    """

    def wrapper(grades: dict[QuestionId, Decimal | None]) -> Decimal | str:
        kwargs = {q: float(g) if g is not None else 0 for q, g in grades.items()}

        try:
            result = func(**kwargs)
            if isinstance(result, (str, Decimal)):
                return result
            try:
                return to_decimal(result)
            except Exception:
                raise TypeError(f"Final grader must return Decimal or str, got {type(result)}")
        except Exception as e:
            log.error(f"Grader raised an exception: {e}", exc_info=True)
            return "error"

    return wrapper


#
# Cursor types - return classroom objects with extra data
#
class ClsQuiz[Opt = Never](NamedTuple):
    classroom: Classroom
    quiz: Quiz


class ClsQuizQuestion[Opt = Never](NamedTuple):
    classroom: Classroom
    quiz: Quiz | Opt
    question: Question | Opt


class ClsQuizSubQuestion(NamedTuple):
    classroom: Classroom
    quiz: Quiz
    submissions: Submissions
    question: Question


class ClsQuizSub(NamedTuple):
    classroom: Classroom
    quiz: Quiz
    submissions: Submissions


OptClsQuizQuestion = ClsQuizQuestion[None]
