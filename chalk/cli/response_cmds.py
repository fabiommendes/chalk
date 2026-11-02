import io
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import opt
import rich
import typer

from ..core import AnyAnswer, Classroom, models
from ..core.answer import json_serialize_any_answer, serialize_any_answer
from ..data import (
    dump_structured_data,
    validate_structured_format,
)
from ..util.path import batch_save
from .util import safe


def add_response_commands(app: typer.Typer) -> None:
    app.command()(extract)


# ==============================================================================
# chalk extract
# ==============================================================================
@safe
def extract(
    loc: Annotated[
        str | None,
        typer.Argument(
            metavar="LOC",
            help=(
                "Location of the questions to separate responses for (e.g. 'quiz1/q1')"
                + "\n\nIf only the quiz is provided, separate all textual questions."
            ),
        ),
    ] = None,
    extension: Annotated[
        str | None,
        typer.Option(
            ...,
            "-e",
            "--ext",
            metavar="EXT",
            help="The extension to use for the exported files.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            ...,
            "-f",
            "--force",
            help="Force overwrite of existing files.",
        ),
    ] = False,
    inline: Annotated[
        bool,
        typer.Option(
            ...,
            "-i",
            "--inline",
            help="Inline answers back into the responses.csv file.",
        ),
    ] = False,
) -> None:
    """
    Move answers from responses.csv to separate files for easier editing or
    vice-versa.
    """

    cls, quiz, question = Classroom.from_prompt(loc)
    if quiz is None:
        rich.print("[red]Error: Quiz not found[/]")
        raise typer.Exit(1)

    subs = quiz.submissions
    if question is None:
        filter = subs.persisted_questions() if inline else subs.inlined_questions()

        if inline:  # We only inline persisted questions
            questions = opt.filter(quiz.get_question(q) for q in filter)
        else:
            questions = (q for q in quiz.iter_questions() if q.type == "text" and q.id in filter)

    else:
        questions = [question]

    if extension is not None:
        extension = normalize_extension(extension)

    save_quiz = False
    for question in questions:
        if extension is not None and extension != question.get_answer_suffix():
            save_quiz = True
            question.answer_suffix = extension
        if inline:
            subs.inline(question)
        else:
            subs.extract(question, force=force)

    if save_quiz:
        quiz.save()

    subs.save()


def normalize_extension(ext: str) -> str:
    """
    Normalize the extension to ensure it starts with a dot.
    """
    ext = ext.strip()
    if ext and ext[0] not in ".-_":
        ext = f".{ext}"
    return ext


#
# Utilities
#
def archive_responses(
    data: dict[str, AnyAnswer | None],
    output_path: Path,
    format: str | None = None,
    normalizer: Callable[[AnyAnswer], str] | None = None,
    suffix: str = "txt",
) -> None:
    if output_path is None:
        rich.print("[red]Error: Output path must be specified when archiving responses[/]")
        raise typer.Exit(1)

    if suffix:
        suffix = suffix.removeprefix(".")
        suffix = f".{suffix}"

    content: dict[Path, str] = {}
    if format is not None:
        format = validate_structured_format(format)

        for item, answer in data.items():
            if answer is None:
                continue
            with io.StringIO() as fd:
                dump_structured_data(json_serialize_any_answer(answer), fd, format=format)
                content[Path(item + suffix)] = fd.getvalue()
    else:
        normalizer = normalizer or serialize_any_answer
        for item, answer in data.items():
            if answer is None:
                continue
            content[Path(item + suffix)] = normalizer(answer)

    batch_save(content, output=output_path, exists="overwrite")


def remove_answer(student_id: str, response: models.Response) -> models.Response:
    """
    Set the answer field of a response to None
    """
    response.answer = None
    return response
