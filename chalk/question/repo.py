from pathlib import Path
from typing import Any, Iterable, Unpack, override

from rich.console import RenderableType
from rich.text import Text

from ..core import models
from ..core.answer import RepoAnswer
from ..core.grader import Graded, Grader, GraderKwargs
from ..core.models import StudentId
from .base import (
    BaseQuestion,
    validate_type,
)
from .renderable import RenderableField


class Repo(BaseQuestion[models.Repo, RepoAnswer]):
    """
    Textual questions have a text-based answer.

    It can be long essays or short answers and they can display text in many
    different forms like plain text, code snippets, mathematical formulas, etc.
    """

    @property
    def plagiarism(self) -> models.Plagiarism | None:
        return self._conf.plagiarism

    def get_answer_extension(self, default: str | None = None) -> str:
        return ""

    def render_answer(self, answer: RepoAnswer, plain: bool = False) -> RenderableType:
        """
        Render the question as a string.
        """
        exists = (self.root / "responses" / answer).exists()
        return Text(f"{answer}/", style="bold green" if exists else "bold dim")

    def get_grader(self) -> Grader[str] | None:
        script = self.get_autograde_script()
        if script is None:
            return None

        from ..autograder.script_grader import ScriptGrader

        raw_grader = ScriptGrader(script=script, question=self, conf=self.get_autograder())

        def repo_grader(
            id: StudentId,
            answer: RepoAnswer,
            /,
            **kwargs: Unpack[GraderKwargs],
        ) -> Graded | None:
            path = self.root / answer
            return raw_grader(id, path, **kwargs)

        return repo_grader

    def validate_answer(self, data: Any) -> RepoAnswer:
        answer = validate_type(data, str)
        if self.conf.required is not None:
            ensure_required(
                self.conf.required,
                path=self.root / answer,
                base=self.quiz.classroom.root,
            )
        return answer

    @override
    def _render_base_fields(self, plain: bool = False) -> Iterable[tuple[str, RenderableField]]:
        yield from super()._render_base_fields(plain)
        if self.conf.required is not None:
            yield "required", "..."


def ensure_required(required: list[str], path: Path, base: Path):
    """
    Ensure that the required paths exist within the given path.
    """
    if not path.exists():
        raise ValueError(f"Path {path.relative_to(base, walk_up=True)} does not exist.")
    if not path.is_dir():
        raise ValueError(f"Path {path.relative_to(base, walk_up=True)} is not a directory.")

    missing: list[Path] = []
    not_dir: list[Path] = []
    for sub in required:
        is_dir = sub.endswith("/")
        sub_path = path / sub
        if not sub_path.exists():
            missing.append(sub_path)
        elif is_dir and not sub_path.is_dir():
            not_dir.append(sub_path)

    if missing or not_dir:
        msg = "Required files/directories are missing or not directories:\n"
        if missing:
            msg += (
                "Missing:\n"
                + "\n".join(f" - {p.relative_to(base, walk_up=True)}" for p in missing)
                + "\n"
            )
        if not_dir:
            msg += (
                "Expect directories:\n"
                + "\n".join(f" - {p.relative_to(base, walk_up=True)}" for p in not_dir)
                + "\n"
            )
        raise ValueError(msg)
