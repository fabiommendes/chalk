from datetime import datetime
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
    file: Annotated[
        str,
        typer.Option(
            ...,
            "--file",
            "-f",
            metavar="NAME",
            help="Path to the local file on each repository containing the answer.",
        ),
    ] = "answer.txt",
    source: Annotated[
        Path,
        typer.Option(
            ...,
            "--source",
            "-s",
            metavar="PATH",
            help="Base path to search repositories",
        ),
    ] = Path("."),
    force: Annotated[
        bool,
        typer.Option(
            ...,
            "--force",
            "-F",
            help="Overwrite of existing answer.",
        ),
    ] = False,
):
    """
    Load answer from files stored at one repository per student.
    """

    responses: dict[StudentId, str] = {}
    (cls, quiz, question) = Classroom.from_prompt(
        quiz_id=quiz_id,
        question_id=question_id,
        on_error=typer.BadParameter,
    )

    if not source.exists():
        raise typer.BadParameter(f"Source path {source} does not exist.")
    if not source.is_dir():
        raise typer.BadParameter(f"Source path {source} is not a directory.")

    for sub_path in source.iterdir():
        if not sub_path.is_dir():
            continue

        try:
            answer_path = sub_path / file
            data = answer_path.read_text()
        except OSError:
            continue

        responses[sub_path.name] = Response(
            answer=data,
            start=datetime.fromtimestamp(answer_path.stat().st_ctime),
            end=datetime.fromtimestamp(answer_path.stat().st_mtime),
        )

    changed = False
    saved = quiz.responses.iter_answers(question=question_id)
    for student_id, response in responses.items():
        saved_response = saved.get(student_id)
        if force or saved_response is None:
            saved[student_id] = response
            changed = True

    quiz.set_responses_for_question(question_id, saved)
    rich.print(quiz.path)

    if changed:
        quiz.save()
    elif not responses:
        rich.print("No responses were found in the source path.")
    else:
        rich.print("No submissions were changed. Use --force to overwrite existing submissions.")


if __name__ == "__main__":
    app()
