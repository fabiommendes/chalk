from pathlib import Path
from typing import Annotated, Literal, Protocol

import typer

from ...core import Quiz

app = typer.Typer()

Action = Literal["copy", "move", "link", "relink"]
type GithubId = str
type StudentId = str


class ActionFn(Protocol):
    def __call__(self, *, source: Path, dest: Path, force: bool = False) -> None: ...


@app.command()
def main(
    quiz_id: Annotated[
        str,
        typer.Argument(
            metavar="ASSIGNMENT",
            help="Quiz id",
        ),
    ],
    question_id: Annotated[
        str,
        typer.Argument(
            metavar="QUESTION",
            help="Question id",
        ),
    ],
):
    """
    Remove question from quiz.
    """

    try:
        quiz = Quiz.load(id=quiz_id)
    except FileNotFoundError:
        raise typer.BadParameter(f"Quiz {quiz_id} does not exist.")

    (quiz.questions or {}).pop(question_id, None)
    for submission in (quiz.submissions or {}).values():
        submission.responses.pop(question_id, None)

    quiz.save()


if __name__ == "__main__":
    app()
