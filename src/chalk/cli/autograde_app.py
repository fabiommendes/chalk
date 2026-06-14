from pathlib import Path
from typing import Annotated

import opt
import rich
import typer

from ..grader import Autograder
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
            "-s",
            "--student",
            metavar="STUDENT",
            help="Specify a student to grade",
        ),
    ] = None,
    sort: Annotated[
        str | None,
        typer.Option(
            ...,
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

    # Prepare autograder
    assignment, question, responses = read_assignment_question_and_responses(
        assignment_id, question_id, student_id
    )
    autograder = Autograder(
        assignment_id=assignment.id,
        question_id=question.id,
        base=question.base_path,
    )
    autograder.prepare()

    # Begin the grading loop
    try:
        for student_id, response in responses.items():
            if not (all or response.grade is None):
                continue

            rich.print(f"Grading student [b yellow]{student_id}[/]", end=" ")
            autograder.autograde(response, student_id)
            if response.grade is None:
                rich.print(" [dim](not graded)[/]")
            else:
                rich.print(f" [dim]({response.grade})[/]")
    finally:
        if not dry_run:
            assignment.save()

    table = assignment.get_grades()
    table.dump(
        output_path,
        sort=sort,
        format=opt.map(validate_table_format, output_format),
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
            "-s",
            "--student",
            metavar="STUDENT",
            help="Specify a student to test",
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
    autograder = Autograder(
        assignment_id=params.assignment.id,
        question_id=params.question.id,
        base=params.question.base_path,
        debug=True,
    )
    autograder.prepare()

    if not params.responses:
        typer.echo("No responses found for the specified question.")
        return

    for student_id, response in params.responses.items():
        typer.echo(f"Grading student {student_id}...")
        validation_errors = autograder.qualify(response, student_id)
        if validation_errors:
            typer.echo(f"  Validation failed: {validation_errors}")
            continue

        autograder.update_response(response, student_id)
        typer.echo(f"  Grade: {response.grade}, Feedback: {response.feedback}")


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


def list_autograder_plugins() -> None:
    """
    List all available autograder plugins.
    """
    # TODO: list autograder plugins
    raise NotImplementedError("Listing autograder plugins is not yet implemented")
