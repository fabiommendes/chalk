from pathlib import Path
from typing import Annotated, Literal, Protocol

import rich
import typer

from ...core import Classroom

app = typer.Typer()

Action = Literal["copy", "move", "link", "relink"]
type GithubId = str
type StudentId = str


class ActionFn(Protocol):
    def __call__(self, *, source: Path, dest: Path, force: bool = False) -> None: ...


@app.command(
    epilog="""
The repositories are expected to be in the format produced by the `gh classroom clone student-repos` command.
"""
)
def main(
    quiz_id: Annotated[
        str,
        typer.Argument(
            ...,
            metavar="QUIZ",
            help="Name of the quiz.",
        ),
    ],
    question_id: Annotated[
        str,
        typer.Argument(
            ...,
            metavar="QUESTION",
            help="Name of the question.",
        ),
    ],
    path: Annotated[
        Path,
        typer.Argument(
            metavar="PATH",
            help="Path to the roster file.",
        ),
    ] = Path("."),
    verbose: Annotated[
        bool,
        typer.Option(
            ...,
            "-v",
            "--verbose",
            help="Print verbose output.",
        ),
    ] = False,
):
    """
    Create the corresponding columns in the submissions.csv file for all
    student submissions in the given repositories.
    """
    if not path.exists():
        raise typer.BadParameter(f"Path does not exist: {path.relative_to(Path.cwd())}")
    if not path.is_dir():
        raise typer.BadParameter(f"Path is not a directory: {path.relative_to(Path.cwd())}")
    if not path.name.endswith("-submissions"):
        msg = f"Path is not a submissions directory: {path.relative_to(Path.cwd())}"
        msg += "\n\nAre you sure you created it using the [b]gh classroom clone student-repos[/] command?"
        msg += "\nPath should end with the suffix '-submissions'."
        raise typer.BadParameter(msg)
    path = path.absolute()

    cls, quiz, question = Classroom.from_prompt(question_id=question_id, quiz_id=quiz_id)
    if not question.type == "repo":
        raise typer.BadParameter(f"Question {question_id} is not a repository question.")

    gh_to_id = {student.github: student.id for student in cls.roster.values()}

    prefix = path.name.removesuffix("submissions")
    for subdir in path.iterdir():
        if not subdir.is_dir() or not subdir.name.startswith(prefix):
            continue

        gh_username = subdir.name.removeprefix(prefix)
        if gh_username not in gh_to_id:
            msg = (
                f"[yellow]Warning:[/] GitHub username [b cyan]{gh_username}[/] not found in roster."
            )
            if verbose:
                rich.print(msg)
            continue

        student_id = gh_to_id[gh_username]
        answer = str(subdir.relative_to(question.root, walk_up=True))
        quiz.submissions.set_answer(answer, question=question, student=student_id, mode="inline")

    quiz.submissions.save()


if __name__ == "__main__":
    app()
