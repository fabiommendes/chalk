import sys
from pathlib import Path
from typing import Annotated

import opt
import rich
import typer

from ..core import Classroom
from ..table import Table, validate_table_format
from .util import safe

app = typer.Typer(help="Manage questions in quizzes.", no_args_is_help=True)


# ==============================================================================
# chalk question list ASSIGNMENT
# ==============================================================================
@app.command(name="list")
@safe
def list_questions(
    quiz_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            help="Quiz identifier (e.g. 'hw1', 'exam1', etc.)",
        ),
    ] = None,
    sort: Annotated[
        str,
        typer.Option(
            ...,
            "-s",
            "--sort",
            help="Sort by id, name, start, or end",
            metavar="COLUMN",
        ),
    ] = "id",
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
    Show the current list of questions in the specified quiz.
    """
    cfg, quiz = Classroom.from_prompt(quiz_id=quiz_id)

    if sort is not None and sort not in {"id", "name", "type", "grade"}:
        rich.print(f"[b red]Invalid sort column: {sort}[/]", file=sys.stderr)
        raise typer.Exit(1)

    rows = []
    ids: list[str] = []
    for id, question in (questions := quiz.get_questions()).items():
        cells = {
            "name": question.name,
            "type": question.type,
            "grade": question.value,
        }

        ids.append(id)
        rows.append(cells)
    total = sum(question.value for question in questions.values()) or None

    table = Table(rows, index=ids)
    table = table.select_columns(["name", "type", "grade"])
    table.dump(
        output_path,
        sort=sort,
        styles={"id": "bold yellow"},
        last_row={"grade": total, "id": "total"},
        format=opt.map(validate_table_format, output_format),
    )


# ==============================================================================
# chalk question show ASSIGNMENT QUESTION
# ==============================================================================
@app.command(name="show")
@safe
def show(
    quiz_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            help="Quiz identifier (e.g. 'hw1', 'exam1', etc.)",
        ),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            metavar="QUESTION",
            help="Question identifier (e.g. 'q1', 'q2', etc.)",
        ),
    ] = None,
    grades: Annotated[
        bool,
        typer.Option(
            ...,
            "-g",
            "--grades",
            help="Show all grades and grading details for this question.",
        ),
    ] = False,
) -> None:
    """
    Show details of a quiz.
    """
    Classroom.from_prompt(quiz_id=quiz_id, question_id=question_id).question.render()


# ==============================================================================
# chalk question merge ASSIGNMENT QUESTION1 QUESTION2
# ==============================================================================
@app.command(name="merge")
@safe
def merge(
    id1: Annotated[
        str,
        typer.Argument(
            ...,
            help="ID of the first quiz to merge",
        ),
    ],
    id2: Annotated[
        str,
        typer.Argument(
            ...,
            help="ID of the second quiz to merge",
        ),
    ],
    output_id: Annotated[
        str | None,
        typer.Option(
            ...,
            "-o",
            "--output",
            help="ID for the merged quiz (defaults to ID1)",
        ),
    ] = None,
) -> None:
    """
    Merge two quizzes into a single quiz file.

    This is useful for merging changes from different branches or collaborators.
    """
    cfg = Classroom.load()
    quiz1 = cfg.prompt_quiz(id1)
    quiz2 = cfg.prompt_quiz(id2)

    if output_id is None:
        output_id = id1 + "-merged"

    msg = f"Merging quizzes '{quiz1.name}' and '{quiz2.name}' into '{output_id}'..."
    print(msg)
    raise NotImplementedError("Quiz merging is not yet implemented")


# ==============================================================================
# chalk question convert ASSIGNMENT QUESTION
# ==============================================================================
@app.command()
@safe
def convert(
    quiz_id: Annotated[
        str | None,
        typer.Argument(metavar="ASSIGNMENT"),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(metavar="QUESTION"),
    ] = None,
    format: Annotated[
        str | None,
        typer.Option(
            ...,
            "-f",
            "--format",
            help="The output format (table, csv, json)",
        ),
    ] = None,
) -> None:
    """
    Show all grades for the given quiz and student.
    """

    _, quiz, question = Classroom.from_prompt(quiz_id=quiz_id, question_id=question_id)

    if format:
        if question.type == format:
            msg = "Question is already in the desired format."
            typer.echo(msg)
            return
        if question.type is not None:
            msg = f"Cannot convert question of type {question.type} to {format}"
            raise ValueError(msg)

        responses = quiz.submissions.iter_answers(question=question)
        rich.print(responses)


# ==============================================================================
# chalk question issues ASSIGNMENT QUESTION
# ==============================================================================
@app.command()
@safe
def issues(
    quiz_id: Annotated[
        str | None,
        typer.Argument(metavar="ASSIGNMENT"),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(metavar="QUESTION"),
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
    fix: Annotated[
        bool,
        typer.Option(
            ...,
            "--fix",
            help="Automatically fix issues if possible (e.g. by inferring missing choices from responses)",
        ),
    ] = False,
) -> None:
    """
    Show all issues for the given question.
    """

    ctx = Classroom.from_prompt(quiz_id=quiz_id, question_id=question_id)
    ctx.question.validate_question()
    # TODO
    raise NotImplementedError

    if not issues:
        rich.print("No issues found with this question 🥳.")
    elif fix:
        ctx.quiz.save()
