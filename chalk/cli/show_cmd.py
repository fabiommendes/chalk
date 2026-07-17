import sys
from pathlib import Path
from typing import Annotated, Any, cast

import opt
import pandas as pd
import rich
import typer

from ..core import AnyAnswer, Classroom, Question, Quiz
from ..core.score import Score
from ..data import (
    dump_spreadsheet,
    dump_structured_data,
    validate_spreadsheet_format,
)
from ..data.core import is_spreadsheet_format, is_structured_format
from ..question import render_answer
from ..table import Table
from ..util.dataframe import DEFAULT_STATS, grades_dataframe_stats
from .util import safe

__all__ = ["show", "add_show_command"]


def add_show_command(app: typer.Typer) -> None:
    app.command(no_args_is_help=False)(show)


@safe
def show(
    loc: Annotated[
        str | None,
        typer.Argument(
            metavar="LOC",
            help="Quiz/question.",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Display detailed information.",
        ),
    ] = False,
    grades: Annotated[
        bool,
        typer.Option(
            "--grades",
            "-g",
            help="Display grades information.",
        ),
    ] = False,
    final: Annotated[
        bool,
        typer.Option(
            "--final",
            help="When outputing a grades file, include only the mapping between student IDs and final grades.",
        ),
    ] = False,
    sort: Annotated[
        str | None,
        typer.Option(
            "--sort",
            "-s",
            help="Sort table by column.",
        ),
    ] = None,
    answer: Annotated[
        str | None,
        typer.Option(
            "--answer",
            "-a",
            metavar="ID",
            help="Show a specific answer by ID.",
        ),
    ] = None,
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file.",
        ),
    ] = None,
    color: Annotated[
        str,
        typer.Option(
            ...,
            "--color",
            metavar="CHOICE",
            help="Control rich text formatting. Options: 'auto', 'yes', 'no'.",
        ),
    ] = "auto",
    total: Annotated[
        bool,
        typer.Option(
            "--total/--no-total",
            help="Include a total column in the grades table.",
        ),
    ] = True,
) -> None:
    """
    Display information about Chalk resources.
    """
    cls, quiz, question = Classroom.from_prompt(loc)

    force_plain = color == "no"
    if color not in {"auto", "yes", "no"}:
        rich.print(f"[b red]Invalid color option: {color}[/]", file=sys.stderr)
        raise typer.Exit(1)

    if question:
        show_question(
            question,
            verbose=verbose,
            grades=grades,
            plain=force_plain,
            answer_for_student=answer,
        )

    elif quiz:
        show_quiz(
            quiz,
            verbose=verbose,
            grades=grades,
            sort=sort,
            format=format,
            output=output,
            final=final,
            total=total,
        )

    else:
        show_classroom(
            cls,
            verbose=verbose,
            grades=grades,
            sort=sort,
            format=format,
            output=output,
            final=final,
            total=total,
        )


def show_question(
    question: Question,
    *,
    verbose: bool,
    grades: bool,
    plain: bool,
    answer_for_student: str | None,
) -> None:
    quiz = question.quiz
    cls = quiz.classroom

    # Show a specific answer
    if answer_for_student is not None:
        student = cls.get_student(answer_for_student, fuzzy=True)
        if student is None:
            rich.print(f"[b red]Student not found: {answer_for_student}[/]", file=sys.stderr)
            raise typer.Exit(1)
        grade = quiz.grades.get_grade(question=question, student=student)
        answer = quiz.submissions.get_answer(question=question, student=student)

        return dump_answer(question, grade, answer, plain)

    # Fallback print question information
    rich.print(question)
    rich.print("\nHint: [dim]use -g to show grades; -a ID to show a specific answer[/]")


def show_quiz(
    quiz: Quiz,
    *,
    verbose: bool,
    grades: bool,
    sort: str | None,
    format: str | None,
    output: Path | None,
    final: bool,
    total: bool,
) -> None:
    # Export the final grades
    if grades and final:
        df = quiz.grades.get_dataframe(total=total)
        return dump_final_grades(df, format, output)

    # Show classroom grades in a specific format
    if grades and (format or output):
        df = quiz.grades.get_dataframe(total=total)
        return dump_grades(df, format, output)

    if grades:
        rich.print(quiz.grades.render(sort=sort or "id", total=total))
        return

    # Fallback
    rich.print(quiz)
    rich.print("\nHint: [dim]use -g to show grades.[/]")


def show_classroom(
    cls: Classroom,
    *,
    verbose: bool,
    grades: bool,
    sort: str | None,
    format: str | None,
    output: Path | None,
    final: bool,
    total: bool,
) -> None:
    # Export the final grades
    if grades and final:
        df = cls.get_grades(total=total)
        return dump_final_grades(df, format, output)

    # Show classroom grades in a specific format
    if grades and (format or output):
        df = cls.get_grades(total=total)
        return dump_grades(df, format, output)

    # Show plain classroom grades
    if grades:
        df = cls.get_grades(total=total)
        stats = grades_dataframe_stats(df)[[*DEFAULT_STATS]]
        extra_rows = [{"id": stat, **stats[stat].to_dict()} for stat in stats]
        table = Table.from_dataframe(df)

        if sort != "id" and sort not in table.columns:
            rich.print(f"[red]Warning:[/] Column '{sort}' not found.", file=sys.stderr)
            sort = "id"

        rich.print(
            table.render(
                extra_rows=extra_rows,
                styles={"id": "bold yellow", "total": "bold blue"},
                empty="No grades available",
                sort=sort,
            )
        )
        return

    rich.print(cls)
    rich.print("\nHint: [dim]use -g to show grades.[/]")


def dump_grades(df: pd.DataFrame, /, format: str | None, output: Path | None):
    table = Table.from_dataframe(df.fillna(None))
    format = format if format is None else validate_spreadsheet_format(format)
    dump_spreadsheet(table, output, format=format, backup=False)


def dump_final_grades(df: pd.DataFrame, /, format: str | None, output: Path | None):
    if format is None or is_structured_format(format):
        data = cast(dict[str, Any], df["final"].to_dict())
        dump_structured_data(data, output, format=format, backup=False)

    elif is_spreadsheet_format(format):
        table = Table.from_dataframe(df[["final"]])
        dump_spreadsheet(table, output, format=format, backup=False)


def dump_answer(
    question: Question,
    grade: Score | None,
    answer: AnyAnswer | None,
    plain: bool,
):
    rich.print(f"[bold green]{question.quiz.name}, {question.name}[/]")
    max_grade = f"/[blue]{question.value}[/]" if question.value is not None else ""
    rich.print(f"[dim]Grade: {opt.unwrap(grade, 'N/A')}[/]{max_grade}")
    if answer is None:
        rich.print("[yellow]No answer found for this question.[/]", file=sys.stderr)
        raise typer.Exit(1)
    rich.print(render_answer(question, answer, plain=plain))
