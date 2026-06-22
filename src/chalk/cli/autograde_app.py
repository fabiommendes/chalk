import time
from pathlib import Path
from typing import Annotated, Any, Literal, Mapping

import errorz as rz
import opt
import rich
import typer
from rich.prompt import Prompt

from ..core import Question, Response
from ..table import validate_table_format
from .util import (
    read_assignment_question_and_responses,
    safe,
)

app = typer.Typer(help="Manage the student roster.", no_args_is_help=True)


# ==============================================================================
# chalk autograde new [ASSIGNMENT QUESTION TEMPLATE]
# ==============================================================================
@app.command(name="create")
@safe
def create(
    assignment_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            metavar="ASSIGNMENT",
            help="Assignment identifier (e.g. 'hw1', 'exam1', etc.)",
        ),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            metavar="QUESTION",
            help="Question identifier",
        ),
    ] = None,
    template: Annotated[
        str | None,
        typer.Argument(
            ...,
            metavar="TEMPLATE",
            help="Autograder template",
        ),
    ] = None,
    list_templates: Annotated[
        bool,
        typer.Option(
            ...,
            "-l",
            "--list-templates",
            help="List available autograder templates",
        ),
    ] = False,
    explain: Annotated[
        bool,
        typer.Option(
            ...,
            "-e",
            "--explain",
            help="Explain the autograder template format",
        ),
    ] = False,
) -> None:
    """
    Create a new autograder script.
    """

    # TODO: autograder creation
    raise NotImplementedError("Autograder creation is not yet implemented")


# ==============================================================================
# chalk autograde run ASSIGNMENT [QUESTION]
# ==============================================================================
@app.command(name="run")
@safe
def run(
    assignment_id: Annotated[
        str,
        typer.Argument(
            ...,
            metavar="ASSIGNMENT",
            help="Assignment identifier (e.g. 'hw1', 'exam1', etc.)",
        ),
    ],
    question_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            metavar="QUESTION",
            help="Question identifier",
        ),
    ] = None,
    auto_yes: Annotated[
        bool,
        typer.Option(
            ...,
            "-y",
            "--yes",
            help="Automatically confirm any prompts during the grading process",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            ...,
            "-d",
            "--dry-run",
            help="Simulate the grading process without making any changes to grades or feedback",
        ),
    ] = False,
    all: Annotated[
        bool,
        typer.Option(
            ...,
            "--all",
            help="Regrade all students, not just those who haven't been graded yet",
        ),
    ] = False,
    student_id: Annotated[
        str | None,
        typer.Option(
            ...,
            "--student",
            metavar="STUDENT",
            help="Specify a student to grade",
        ),
    ] = None,
    sort: Annotated[
        str | None,
        typer.Option(
            ...,
            "-s",
            "--sort",
            metavar="FIELD",
            help="Sort the output by the specified field",
        ),
    ] = None,
    output_format: Annotated[
        str | None,
        typer.Option(
            ...,
            "-f",
            "--format",
            metavar="FORMAT",
            help="Specify the output format (e.g. 'table', 'json', etc.)",
        ),
    ] = None,
    output_path: Annotated[
        Path | None,
        typer.Option(
            ...,
            "-o",
            "--output",
            metavar="PATH",
            help="Specify a file to save the output to",
        ),
    ] = None,
    list_plugins: Annotated[
        bool,
        typer.Option(
            ...,
            "-l",
            "--list-plugins",
            help="List available autograder plugins without running any grading",
        ),
    ] = False,
) -> None:
    """
    Run the autograder for the specified assignment and question.
    """
    if list_plugins:
        list_autograder_plugins()
        return

    params = read_assignment_question_and_responses(
        assignment_id, question_id, student_id
    )
    run_or_try(
        question=params.question,
        responses=params.responses,
        regrade=all,
        dry_run=dry_run,
        output_format=output_format,
        output_path=output_path,
        sort=sort,
    )


# ==============================================================================
# chalk autograde try ASSIGNMENT [QUESTION]
# ==============================================================================
@app.command(name="try")
@safe
def try_grading(
    assignment_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            metavar="ASSIGNMENT",
            help="Assignment identifier (e.g. 'hw1', 'exam1', etc.)",
        ),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            metavar="QUESTION",
            help="Question identifier",
        ),
    ] = None,
    student_id: Annotated[
        str | None,
        typer.Option(
            ...,
            "--student",
            metavar="STUDENT",
            help="Specify a student to test",
        ),
    ] = None,
    sort: Annotated[
        str | None,
        typer.Option(
            ...,
            "-s",
            "--sort",
            metavar="FIELD",
            help="Sort the output by the specified field",
        ),
    ] = None,
    output_format: Annotated[
        str | None,
        typer.Option(
            ...,
            "-f",
            "--format",
            metavar="FORMAT",
            help="Specify the output format (e.g. 'table', 'json', etc.)",
        ),
    ] = None,
    output_path: Annotated[
        Path | None,
        typer.Option(
            ...,
            "-o",
            "--output",
            metavar="PATH",
            help="Specify a file to save the output to",
        ),
    ] = None,
) -> None:
    """
    Run the autograder for the specified assignment and question on a single test
    submission. It is intended for testing and debugging the autograder script and
    it does not affect the actual grades or feedback.
    """

    params = read_assignment_question_and_responses(
        assignment_id, question_id, student_id
    )
    run_or_try(
        question=params.question,
        responses=params.responses,
        regrade=True,
        dry_run=True,
        output_format=output_format,
        output_path=output_path,
        sort=sort,
        interactive=True,
    )


# ==============================================================================
# chalk autograde list [ASSIGNMENT [QUESTION]]
# ==============================================================================
@app.command(name="list")
@safe
def list_autograded(
    assignment_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            metavar="ASSIGNMENT",
            help="Assignment identifier (e.g. 'hw1', 'exam1', etc.)",
        ),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            metavar="QUESTION",
            help="Question identifier",
        ),
    ] = None,
) -> None:
    """
    List all autograded questions in the specified assignment and display
    statistics about the grading process.
    """

    # TODO: list autograded questions
    raise NotImplementedError("Listing autograded questions is not yet implemented")


#
# Utility functions
#
def list_autograder_plugins() -> None:
    """
    List all available autograder plugins.
    """
    # TODO: list autograder plugins
    raise NotImplementedError("Listing autograder plugins is not yet implemented")


def run_or_try(
    question: Question,
    responses: dict[str, Response],
    *,
    regrade: bool,
    dry_run: bool,
    output_format: str | None,
    output_path: Path | None,
    sort: str | None,
    interactive: bool = False,
    save_period: float = 5.0,
    grader_options: Mapping[str, Any] = {},
) -> None:
    # Prepare autograder
    assignment = opt.unwrap(question.get_assignment())

    grader = question.get_grader()
    if rz.is_err(grader):
        typer.echo(f"No autograder found: {grader}")
        return

    question.validate_responses(responses, inplace=True)

    # Begin the grading loop saving every 5s
    save_schedule = time.time() + 5
    force_skip_view = False
    yn_response: bool | None = True
    try:
        for student_id, response in responses.items():
            if not (regrade or response.grade is None):
                continue

            if response.answer is None and interactive:
                rich.print(f"Empty response: [b yellow]{student_id}[/]")
            if response.answer is None:
                continue

            # Display question
            end = "\n" if interactive and not force_skip_view else " "
            rich.print(f"Grading student [b yellow]{student_id}[/]", end=end)

            answer: Any = question.validate_answer(response.answer)
            if rz.is_err(answer):
                rich.print(f"[red dim](invalid: {answer.error})[/]")
                continue

            # Show response, if interactive
            if (
                not force_skip_view
                and interactive
                and (yn_response := yn_prompt("View response?", "y"))
            ):
                question.display_answer(answer)
            if interactive and not force_skip_view:
                rich.print(f"Graded student: [yellow b]{student_id}[/]", end=" ")
            force_skip_view = yn_response is None

            outcome = grader(student_id, answer, **grader_options)

            if outcome is None or outcome.score is None:
                rich.print(" [dim](not graded)[/]")
            else:
                if response.grade is not None and response.grade != outcome.score:
                    rich.print(f" [dim]({response.grade} -> {outcome.score})[/]")
                else:
                    rich.print(f" [dim]({outcome.score})[/]")
                response.grade = outcome.grade
                response.feedback = opt.coalesce(outcome.feedback, response.feedback)

            if time.time() >= save_schedule and not dry_run:
                assignment.save()
                save_schedule = time.time() + save_period
    finally:
        if not dry_run:
            assignment.save()

    table = assignment.get_grades(total="total")
    table = table.select_rows([id for (id, _) in responses.items()])
    table.dump(
        output_path,
        sort=sort,
        format=opt.map(validate_table_format, output_format),
    )


def yn_prompt(message: str, default: Literal["y", "n", "never"] = "y") -> bool | None:
    match Prompt.ask(message, choices=["y", "n", "never"], default=default):
        case "y":
            return True
        case "n":
            return False
        case "never":
            return None
        case _:
            raise RuntimeError("Invalid choice")
