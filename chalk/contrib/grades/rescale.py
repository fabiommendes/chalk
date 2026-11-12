from pathlib import Path
from typing import Annotated, Literal, Protocol

import opt
import rich
import typer

from ...core import Classroom, score

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
            metavar="QUIZ",
            help="Quiz id",
        ),
    ],
    question_id: Annotated[
        str | None,
        typer.Argument(
            metavar="QUESTION",
            help="Question id",
        ),
    ] = None,
):
    """
    Load answer from files stored at one repository per student.
    """

    cls = Classroom.load()
    quiz = cls.get_quiz(quiz_id)
    if quiz is None:
        raise typer.BadParameter(f"Quiz {quiz_id} does not exist.")

    for qid in [question_id] if question_id else quiz.get_question_ids():
        question = opt.unwrap(quiz.get_question(qid))
        quiz.grades.update_score({qid: lambda _, x, q=question: score.div(x, q.value)})

    rich.print(quiz.grades)
    quiz.grades.save()


if __name__ == "__main__":
    app()
