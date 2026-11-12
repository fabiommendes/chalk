import sys
from pathlib import Path
from typing import Annotated, Any, cast

import opt
import pandas as pd
import rich
import typer

from ..core import AnyAnswer, Classroom, Question, Quiz, Student
from ..core.answer import serialize_any_answer
from ..core.score import Score
from ..data import (
    dump_data,
    dump_spreadsheet,
    dump_structured_data,
    validate_spreadsheet_format,
)
from ..data.core import is_spreadsheet_format, is_structured_format
from ..info import get_project_info
from ..question import render_answer
from ..table import Table, validate_table_format
from ..util.dataframe import DEFAULT_STATS, grades_dataframe_stats
from .util import parse_sort, safe

__all__ = ["show", "add_show_command"]

ANSWER_TEXT_FORMATS = ("md", "markdown", "txt", "text")


def add_show_command(app: typer.Typer) -> None:
    app.command(no_args_is_help=False)(show)


@safe
def show(
    loc: Annotated[
        str | None,
        typer.Argument(
            metavar="LOC",
            help="Quiz or quiz/question (e.g. 'p1', 'p1/q1'). Empty shows the classroom.",
        ),
    ] = None,
    grades: Annotated[
        bool,
        typer.Option("--grades", "-g", help="Show grades instead of the description."),
    ] = False,
    roster: Annotated[
        bool,
        typer.Option("--roster", help="Show the roster. Takes no LOC."),
    ] = False,
    answers: Annotated[
        bool,
        typer.Option("--answers", help="Show the answers to a question (LOC is quiz/question)."),
    ] = False,
    student: Annotated[
        str | None,
        typer.Option(
            "--student",
            metavar="ID",
            help="Only this student: its answer to a question, or its row of grades with -g.",
        ),
    ] = None,
    final: Annotated[
        bool,
        typer.Option(
            "--final",
            help="With -g and -f/-o, write only the mapping from student ids to final grades.",
        ),
    ] = False,
    sort: Annotated[
        str | None,
        typer.Option(
            "--sort",
            "-s",
            metavar="COLUMN",
            help="Sort tables by this column. A '-' prefix sorts in descending order.",
        ),
    ] = None,
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            metavar="FORMAT",
            help="table, csv, json or yaml. --answers also takes md.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            metavar="FILE",
            help="Write to this file. The format comes from the extension if -f is missing.",
        ),
    ] = None,
    color: Annotated[
        str,
        typer.Option(
            "--color",
            metavar="CHOICE",
            help="Rich text formatting of answers: auto, yes or no.",
        ),
    ] = "auto",
    total: Annotated[
        bool,
        typer.Option("--total/--no-total", help="Include a total column in grade tables."),
    ] = True,
) -> None:
    """
    Show the classroom, a quiz, a question, the roster or the answers.

    Without LOC, shows the classroom and its quizzes; with a quiz, its
    questions; with quiz/question, the question. -g shows grades instead.
    """
    if color not in {"auto", "yes", "no"}:
        raise typer.BadParameter(f"invalid choice: {color}", param_hint="--color")
    if roster and (loc or grades or answers or student):
        raise typer.BadParameter(
            "--roster takes no LOC and no --grades, --answers or --student",
            param_hint="--roster",
        )

    cls, quiz, question = Classroom.from_prompt(loc, check_exist=loc is not None)

    if answers and question is None:
        raise typer.BadParameter("--answers needs a question: QUIZ/QUESTION", param_hint="LOC")
    if answers and grades:
        raise typer.BadParameter("use --answers or --grades, not both", param_hint="--answers")
    if student is not None and question is None and not grades:
        raise typer.BadParameter(
            "--student needs a question (QUIZ/QUESTION) or --grades", param_hint="--student"
        )

    who = None if student is None else find_student(cls, student)

    if roster:
        show_roster(cls, sort=sort, format=format, output=output)
    elif grades:
        df = grades_dataframe(cls, quiz, question, total=total)
        if who is not None:
            df = df.loc[df.index.intersection([who.id])]
        if final:
            dump_final_grades(df, format, output)
        elif format or output:
            dump_grades(df, format, output)
        else:
            print_grades(df, sort=sort)
    elif question is not None and who is not None:
        show_answer(question, who, plain=color == "no")
    elif question is not None and answers:
        show_answers(question, format=format, output=output)
    elif question is not None:
        if format or output:
            raise typer.BadParameter(
                "a question is not a table; use -g or --answers", param_hint="--format"
            )
        rich.print(question)
        rich.print(
            "\nHint: [dim]-g shows grades, --answers the answers, --student ID one answer[/]"
        )
    elif quiz is not None:
        show_quiz(quiz, sort=sort, format=format, output=output)
    else:
        show_classroom(cls, sort=sort, format=format, output=output)


def find_student(cls: Classroom, student_id: str) -> Student:
    student = cls.get_student(student_id, fuzzy=True)
    if student is None:
        raise typer.BadParameter(f"student not found: {student_id}", param_hint="--student")
    return student


#
# Descriptions
#
def show_classroom(
    cls: Classroom, *, sort: str | None, format: str | None, output: Path | None
) -> None:
    if format in ("json", "yaml") or (
        format is None and opt.map(suffix_of, output) in ("json", "yaml")
    ):
        dump_structured_data(get_project_info(), output, format=format, backup=False)
        return

    rows: list[dict[str, Any]] = []
    ids: list[str] = []
    for quiz in cls.iter_quizzes():
        ids.append(quiz.id)
        rows.append(
            {
                "name": quiz.name,
                "start": quiz.start,
                "end": quiz.end,
                "questions": len(quiz.get_question_ids()),
            }
        )
    table = Table(rows, index=ids).select_columns(["name", "start", "end", "questions"])
    column, reverse = parse_sort(sort)

    if format or output:
        table.dump(
            output, format=opt.map(validate_table_format, format), sort=column, reverse=reverse
        )
        return

    students = len(cls.get_roster())
    rich.print(f"[b]{cls.name}[/] ({cls.teacher}), {students} students\n")
    rich.print(
        table.render(
            styles={"id": "bold yellow"}, sort=column, reverse=reverse, empty="No quizzes yet."
        )
    )
    rich.print("\nHint: [dim]-g shows grades, --roster the roster, LOC a quiz[/]")


def show_quiz(quiz: Quiz, *, sort: str | None, format: str | None, output: Path | None) -> None:
    column, reverse = parse_sort(sort)
    if format or output:
        quiz.question_table().dump(
            output, format=opt.map(validate_table_format, format), sort=column, reverse=reverse
        )
        return

    rich.print(quiz.render(sort=column, reverse=reverse))
    rich.print("\nHint: [dim]-g shows grades, QUIZ/QUESTION a question[/]")


def show_roster(
    cls: Classroom, *, sort: str | None, format: str | None, output: Path | None
) -> None:
    table = cls.get_roster().table()
    column, reverse = parse_sort(sort or "id")
    if column != "id" and column not in table.columns:
        raise typer.BadParameter(f"no column {column!r} in the roster", param_hint="--sort")

    table.dump(
        output,
        format=opt.map(validate_table_format, format),
        styles={"email": "dim white", "id": "bold yellow"},
        sort=column,
        reverse=reverse,
    )


#
# Answers
#
def show_answer(question: Question, student: Student, plain: bool) -> None:
    grades = question.quiz.grades
    grade = grades.get_grade(question=question, student=student)
    answer = question.quiz.submissions.get_answer(question=question, student=student)
    dump_answer(question, grade, answer, plain)


def show_answers(question: Question, *, format: str | None, output: Path | None) -> None:
    answers = dict(question.quiz.submissions.iter_answers(question=question))

    if format is None and output is not None:
        format = suffix_of(output)
    if format is None:
        format = "md"

    if is_structured_format(format):
        dump_structured_data(answers, output, format=format)
    elif is_spreadsheet_format(format):
        table = Table(
            [
                {"id": id, "answer": opt.map(serialize_any_answer, answer)}
                for id, answer in answers.items()
            ]
        )
        dump_spreadsheet(table, output, format=format)
    elif format in ANSWER_TEXT_FORMATS:
        parts = []
        for student_id, answer in answers.items():
            parts.append(f"## {student_id}\n")
            parts.append(serialize_any_answer(answer))
            parts.append("---")
        if parts:
            parts.pop()
        dump_data("\n".join(parts), output, format=format, word_wrap=True)
    else:
        raise typer.BadParameter(f"unsupported format: {format}", param_hint="--format")


def dump_answer(
    question: Question,
    grade: Score | None,
    answer: AnyAnswer | None,
    plain: bool,
):
    rich.print(f"[bold green]{question.quiz.name}, {question.name}[/]")
    max_grade = f"/[blue]{question.value}[/]" if question.value is not None else ""
    rich.print(f"[dim]Grade: {opt.unwrap(grade, 'NA')}[/]{max_grade}")
    if answer is None:
        rich.print("[yellow]No answer found for this question.[/]", file=sys.stderr)
        raise typer.Exit(1)
    rich.print(render_answer(question, answer, plain=plain))


#
# Grades
#
def grades_dataframe(
    cls: Classroom, quiz: Quiz | None, question: Question | None, *, total: bool
) -> pd.DataFrame:
    if question is not None:
        return question.quiz.grades.get_dataframe()[[question.id]]
    if quiz is not None:
        return quiz.grades.get_dataframe(total=total)
    return cls.get_grades(total=total)


def print_grades(df: pd.DataFrame, *, sort: str | None) -> None:
    stats = grades_dataframe_stats(df)[[*DEFAULT_STATS]]
    extra_rows = [{"id": stat, **stats[stat].to_dict()} for stat in stats]
    table = Table.from_dataframe(df)

    column, reverse = parse_sort(sort)
    if column not in (None, "id") and column not in table.columns:
        rich.print(f"[red]Warning:[/] Column '{column}' not found.", file=sys.stderr)
        column = "id"

    rich.print(
        table.render(
            extra_rows=extra_rows,
            styles={"id": "bold yellow", "total": "bold blue"},
            empty="No grades available",
            sort=column,
            reverse=reverse,
        )
    )


def dump_grades(df: pd.DataFrame, /, format: str | None, output: Path | None):
    table = Table.from_dataframe(df.fillna(None))
    format = format if format is None else validate_spreadsheet_format(format)
    dump_spreadsheet(table, output, format=format, backup=False)


def dump_final_grades(df: pd.DataFrame, /, format: str | None, output: Path | None):
    if "final" not in df.columns:
        raise typer.BadParameter("these grades have no final column", param_hint="--final")
    if format is None or is_structured_format(format):
        data = cast(dict[str, Any], df["final"].to_dict())
        dump_structured_data(data, output, format=format, backup=False)
    elif is_spreadsheet_format(format):
        table = Table.from_dataframe(df[["final"]])
        dump_spreadsheet(table, output, format=format, backup=False)


def suffix_of(path: Path) -> str:
    return path.suffix.removeprefix(".").lower()
