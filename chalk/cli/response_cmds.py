import io
from pathlib import Path
from typing import Annotated, Callable

import opt
import rich
import typer
from rich.prompt import Prompt

from ..core import AnyAnswer, Classroom, Question, Quiz, StudentId, models
from ..core.answer import json_serialize_any_answer, serialize_any_answer
from ..data import (
    dump_structured_data,
    validate_structured_format,
)
from ..question import render_answer
from ..transform import create_script as create_transform_script
from ..transform import list_transforms, load_transform
from ..util.external import open_editor
from ..util.path import batch_save
from .util import safe


def add_response_commands(app: typer.Typer) -> None:
    app.command()(transform)
    app.command()(extract)


# ==============================================================================
# chalk transform
# ==============================================================================
@safe
def transform(
    quiz_id: Annotated[
        str | None,
        typer.Argument(
            metavar="ASSIGNMENT",
        ),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(
            metavar="QUESTION",
        ),
    ] = None,
    student_id: Annotated[
        str | None,
        typer.Option(
            ...,
            "-s",
            "--student",
            help="Filter student responses by ID",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(..., "--force", help="Apply the transformation without confirmation"),
    ] = False,
    transform: Annotated[
        str | None,
        typer.Option(
            ...,
            "-t",
            "--transform",
            help="The transformation to apply",
        ),
    ] = None,
    list_transforms_: Annotated[
        bool,
        typer.Option(
            ...,
            "-l",
            "--list",
            help="List available transformations without applying any changes",
        ),
    ] = False,
    new_transform_: Annotated[
        str | None,
        typer.Option(
            ...,
            "-n",
            "--new",
            help="Create a new transformation script. You may add a suffix (like .sh or .py) to specify the script type",
        ),
    ] = None,
) -> None:
    """
    Apply transformations to responses for the given question.
    """
    is_system_cmd = not quiz_id and not question_id

    if (list_transforms_ or new_transform_) and not is_system_cmd:
        msg = "[red]Error: The --list and --new options cannot be applied to a specific quiz or question[/]"
        rich.print(msg)
        raise typer.Exit(1)

    elif list_transforms_:
        if any([student_id, transform, force, new_transform_]):
            msg = "[red]Error: The --list option cannot be combined with other options[/]"
            rich.print(msg)
            raise typer.Exit(1)

        for transform_fn in list_transforms():
            rich.print(f"[green]{transform_fn}[/] - [dim]{transform_fn.description}[/]")

    elif new_transform_:
        if any([student_id, transform, list_transforms_]):
            msg = "[red]Error: The --new can only be combined with --force[/]"
            rich.print(msg)
            raise typer.Exit(1)

        name, _, suffix = new_transform_.rpartition(".")
        new = create_transform_script(name, suffix=suffix or "py")
        rich.print(f"Created new transform script at [green]{new.path}[/]")

        if (
            not force
            and Prompt.ask("Do you want to open the script now?", choices=["y", "n"], default="y")
            == "y"
        ):
            open_editor(opt.unwrap(new.path))

    elif transform:
        _, quiz, question = Classroom.from_prompt(quiz_id=quiz_id, question_id=question_id)
        apply_transforms(
            quiz,
            question,
            student_id=student_id,
            transform_name=transform,
            force=force,
        )

    else:
        raise RuntimeError("invalid branch")


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
def apply_transforms(
    quiz: Quiz,
    question: Question,
    student_id: str | None,
    transform_name: str,
    force: bool,
) -> None:
    has_changes = False
    transform = load_transform(transform_name)
    if transform is None:
        rich.print(f"[red]Error: Invalid transform: '{transform_name}'[/]")
        raise typer.Exit(1)

    if student_id:
        raise NotImplementedError("Filtering by student ID is not yet implemented.")

    trasformed: dict[StudentId, AnyAnswer] = {}
    for student_id, answer in quiz.submissions.iter_answers(question=question):
        original_answer = answer
        transformed_answer = transform(original_answer)
        if transformed_answer is None:
            continue

        if force:
            trasformed[student_id] = transformed_answer
            has_changes = True
            continue

        rich.print(f"\n[bold]Student ID:[/] {student_id}")
        rich.print(render_answer(question, transformed_answer))
        rich.print()

        prompt = Prompt.ask("Accept?", choices=["y", "n", "all", "none"], default="y")

        if prompt in ["all", "y"]:
            trasformed[student_id] = transformed_answer
            has_changes = True
        if prompt == "all":
            force = True
        if prompt == "none":
            break

    if has_changes:
        for student_id, answer in trasformed.items():
            quiz.submissions.set_answer(answer, student=student_id, question=question)
        quiz.save()


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
