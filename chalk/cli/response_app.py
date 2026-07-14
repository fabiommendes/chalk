import io
import sys
from pathlib import Path
from typing import Annotated, Callable

import opt
import rich
import typer
from rich.prompt import Prompt

from ..core import AnyAnswer, Classroom, Question, Quiz, models
from ..core.answer import json_serialize_answer, serialize_answer
from ..data import (
    dump_structured_data,
    validate_structured_format,
)
from ..question import render_answer
from ..question import serialize_answer as question_serialize_answer
from ..transform import create_script as create_transform_script
from ..transform import list_transforms, load_transform
from ..util.external import open_editor
from ..util.path import batch_save
from .util import safe

app = typer.Typer()


# ==============================================================================
# chalk response view
# ==============================================================================
@app.command()
@safe
def view(
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
        typer.Argument(
            metavar="STUDENT",
        ),
    ] = None,
    plain: Annotated[
        bool,
        typer.Option(
            ...,
            "--plain",
            help="Print the answer without rich formatting",
        ),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option(
            ...,
            "-o",
            "--output",
            help="Write the answer to a file instead of printing it to the console",
        ),
    ] = None,
) -> None:
    """
    List all responses for the given question.
    """

    cls, quiz, question = Classroom.from_prompt(quiz_id=quiz_id, question_id=question_id)
    student = cls.prompt_student(student_id, fuzzy=True)
    answer = quiz.get_answer(question, student=student)

    # Show name
    if output is None:
        max_grade = f"/[blue]{question.value}[/]" if question.value is not None else ""

        rich.print(f"[bold green]{quiz.name}, {question.name}[/]")
        # FIXME: rich.print(f"[dim]Grade: {opt.unwrap(response.grade, 'N/A')}[/]{max_grade}")
        rich.print()

    if output is None:
        rich.print(render_answer(question, answer, plain=plain))
    elif answer is not None:
        # FIXME: correct dump file
        output.write_text(str(answer))
    else:
        rich.print("[yellow]No answer found for this question.[/]", file=sys.stderr)
        raise typer.Exit(1)


# ==============================================================================
# chalk response transform
# ==============================================================================
@app.command()
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
# chalk response separate
# ==============================================================================
@app.command()
@safe
def separate(
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
    suffix: Annotated[
        str | None,
        typer.Option(
            ...,
            "-s",
            "--suffix",
            help="The suffix to use for the exported files.",
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
) -> None:
    """
    Extract all answers from the responses.csv and write them to separate files
    in the question directory.
    """
    quiz, question = Classroom.from_prompt(quiz_id=quiz_id, question_id=question_id)[1:]

    old_suffix = question.get_answer_extension()
    new_suffix = suffix or question.get_answer_extension(suffix)
    if new_suffix is None:
        msg = "The --suffix/-s option is required when the question has no default suffix."
        raise typer.BadParameter(msg)

    # Load responses and save them on separate files
    root = question.get_root(mkdir=True)
    for student_id, answer in quiz.iter_answers(question, inline_only=True):
        file_path = root / f"{student_id}.{new_suffix}"
        if not force and file_path.exists():
            rich.print(f"[yellow]Skipping: {file_path.name}[/]")
            continue

        src = question_serialize_answer(question, answer)
        file_path.write_text(src)

    if old_suffix != new_suffix:
        question.answer_suffix = new_suffix
        quiz.save()

    print(old_suffix, new_suffix)

    # Update the responses.csv to reflect that the answers are now persisted
    quiz.submissions.update_responses(question.id, remove_answer)


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

    for student_id, response in quiz.get_responses_for_question(question).items():
        original_answer = response.answer
        transformed_answer = transform(original_answer)

        if transformed_answer is None:
            continue

        if force:
            response.answer = transformed_answer
            has_changes = True
            continue

        rich.print(f"\n[bold]Student ID:[/] {student_id}")
        rich.print(render_answer(question, transformed_answer))
        rich.print()

        prompt = Prompt.ask("Accept?", choices=["y", "n", "all", "none"], default="y")

        if prompt in ["all", "y"]:
            response.answer = transformed_answer
            has_changes = True
        if prompt == "all":
            force = True
        if prompt == "none":
            break

    if has_changes:
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
                dump_structured_data(json_serialize_answer(answer), fd, format=format)
                content[Path(item + suffix)] = fd.getvalue()
    else:
        normalizer = normalizer or serialize_answer
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
