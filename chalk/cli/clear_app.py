import shutil

import rich
import typer

from chalk.core import Classroom

from .util import safe

__all__ = ["clear", "add_clear_command"]


def add_clear_command(app: typer.Typer) -> None:
    app.command(no_args_is_help=False)(clear)


@safe
def clear() -> None:
    """
    Clear the files chalk generates: the cache of the autograder profiles.

    The roster, quizzes, submissions and grades are never removed. Files kept
    by `autograde --keep-files` live in the system temp directory and stay.
    """
    clear_autograder_files()


def clear_autograder_files() -> None:
    """
    Remove the cache of the autograder profiles and the old tmp-* folders of
    the questions. The next autograde rebuilds the cache.

    Files kept by `autograde --keep-files` live in the system temp directory
    and are left alone.
    """
    cfg = Classroom.load()
    cache = cfg.root / ".chalk" / "cache"
    if cache.is_dir():
        shutil.rmtree(cache)
        rich.print(f"Removed [b]{cache}[/]")
    for quiz in cfg.iter_quizzes():
        for question in quiz.get_questions().values():
            question.clear_autograder_files()
