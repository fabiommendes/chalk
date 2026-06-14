import sys
from pathlib import Path
from typing import Annotated

import opt
import rich
import typer
from rich.prompt import Prompt

from ..conf import open_editor
from ..core import Assignment, Question
from ..transform import create_script as create_transform_script
from ..transform import list_transforms, load_transform
from .util import (
    read_assignment_and_question,
    read_assignment_question_and_response,
    safe,
)

app = typer.Typer()


# ==============================================================================
# chalk response view
# ==============================================================================
@app.command()
@safe
def view(
    assignment_id: Annotated[
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

    assignment, question, response = read_assignment_question_and_response(
        assignment_id,
        question_id,
        student_id=student_id,
    )

    if output is None and not plain:
        max_grade = f"/[blue]{question.grade}[/]" if question.grade is not None else ""

        rich.print(f"[bold green]{assignment.name}, {question.title}[/]")
        rich.print(f"[dim]Grade: {opt.unwrap_or(response.grade, 'N/A')}[/]{max_grade}")
        rich.print()

    if output is None:
        question.display_answer(response.answer, rich=not plain)
    elif response.answer:
        output.write_text(response.answer)
    else:
        rich.print("[yellow]No answer found for this question.[/]", file=sys.stderr)
        raise typer.Exit(1)


# ==============================================================================
# chalk response transform
# ==============================================================================
@app.command()
@safe
def transform(
    assignment_id: Annotated[
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
        typer.Option(
            ..., "--force", help="Apply the transformation without confirmation"
        ),
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
    is_system_cmd = not assignment_id and not question_id

    if (list_transforms_ or new_transform_) and not is_system_cmd:
        msg = "[red]Error: The --list and --new options cannot be applied to a specific assignment or question[/]"
        rich.print(msg)
        raise typer.Exit(1)

    elif list_transforms_:
        if any([student_id, transform, force, new_transform_]):
            msg = (
                "[red]Error: The --list option cannot be combined with other options[/]"
            )
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
            and Prompt.ask(
                "Do you want to open the script now?", choices=["y", "n"], default="y"
            )
            == "y"
        ):
            open_editor(opt.unwrap(new.path))

    elif transform:
        assignment, question = read_assignment_and_question(assignment_id, question_id)
        apply_transforms(
            assignment,
            question,
            student_id=student_id,
            transform_name=transform,
            force=force,
        )

    else:
        raise RuntimeError("invalid branch")


#
# Utilities
#
def apply_transforms(
    assignment: Assignment,
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

    for student_id, response in assignment.get_responses_for_question(question).items():
        original_answer = response.answer
        transformed_answer = transform(original_answer)

        if transformed_answer is None:
            continue

        if force:
            response.answer = transformed_answer
            has_changes = True
            continue

        rich.print(f"\n[bold]Student ID:[/] {student_id}")
        question.display_answer(transformed_answer, rich=True)
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
        assignment.save()
