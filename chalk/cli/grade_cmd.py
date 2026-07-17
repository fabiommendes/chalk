from collections import deque
from typing import Annotated

import rich
import typer
from rich.columns import Columns
from rich.panel import Panel
from rich.prompt import Prompt

from ..core import Score, StudentId, score
from ..info import Classroom
from ..question import render_answer
from .util import safe


def add_grade_cmd(app: typer.Typer) -> None:
    app.command()(grade)


SCORE_ALIASES: dict[str, Score] = {
    "0": score.MIN_SCORE,
    "1": score.MAX_SCORE,
    "t": score.MAX_SCORE,
    "f": score.MIN_SCORE,
    "-1": -score.MAX_SCORE,
    "h": score.HALF_SCORE,
    "-h": -score.HALF_SCORE,
    "q1": score.QUARTER_SCORE,
    "-q1": -score.QUARTER_SCORE,
    "q3": score.THREE_QUARTERS_SCORE,
    "-q3": -score.THREE_QUARTERS_SCORE,
    "t1": score.THIRD_SCORE,
    "-t1": -score.THIRD_SCORE,
    "t2": score.TWO_THIRDS_SCORE,
    "-t2": -score.TWO_THIRDS_SCORE,
}


@safe
def grade(
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
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force regrading even if responses already have grades",
        ),
    ] = False,
    all: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Grade all responses, even if they already have grades",
        ),
    ] = False,
    width: Annotated[
        int,
        typer.Option(
            "--width",
            "-w",
            help="Width of the answer display panel",
            min=20,
            max=200,
        ),
    ] = 80,
):
    """
    Manually grade responses for a question.
    """

    cls, quiz, question = Classroom.from_prompt(loc, check_exist=True)
    answers = dict(quiz.submissions.iter_answers(question=question))
    grades = dict(quiz.grades.iter_scores(question=question))
    if not all:
        answers = {k: v for k, v in answers.items() if grades.get(k) is None}

    iter = 0
    N = len(answers)
    rich.print(f"[b]Grading {N} responses for question [cyan]{quiz.id}/{question.id}[/]")

    queue = deque(enumerate(sorted(answers.items()), start=1))
    undo = deque()

    update_scores: dict[StudentId, Score] = {}

    try:
        while queue:
            iter, (student_id, answer) = item = queue.popleft()
            undo.append(item)
            score = grades.get(student_id)

            # Display answer
            print()
            title = f"[b]Student {iter}/{N}: [yellow]{student_id}[/][/b]"
            if score is not None:
                title += f" [b red](score: {score})[/]"

            rich.print(
                Panel(
                    render_answer(question, answer),
                    border_style="blue",
                    title=title,
                    width=min(width, rich.get_console().width),
                )
            )

            try:
                new_score = ask_value(score)
            except UndoOperation:
                if len(undo) < 2:
                    rich.print("[red]No previous response to undo.[/]")
                    queue.appendleft(undo.pop())
                    continue
                queue.appendleft(undo.pop())
                queue.appendleft(undo.pop())
                continue
            except ShowHelp:
                show_help()
                queue.appendleft(undo.pop())
                continue

            if score != new_score and new_score is not None:
                update_scores[student_id] = new_score
                rich.print(f"[green]Score updated to {float(new_score)}[/]")

    finally:
        for student_id, new_score in update_scores.items():
            quiz.grades.set_score(new_score, question=question, student=student_id)
        if update_scores:
            quiz.grades.save()


def show_help() -> None:
    rich.print("[b]Enter a score between 0 and 1, or use one of the following aliases:[/]")
    for alias, value in SCORE_ALIASES.items():
        rich.print(
            Columns(
                [f"[b yellow]{alias:>4}[/]", "=", f"{float(value):>5.2f}"],
                expand=False,
                equal=False,
            ),
        )
    rich.print("[b]Enter 'u' to undo the previous response.[/]")
    rich.print("[b]Integral numbers (except 1) are interpreted as percentages.[/]")
    rich.print("[b]Press Ctrl+C to exit grading.[/]")


def ask_value(score) -> Score | None:
    value = Prompt.ask(
        "[b]Score [0-1][/]",
        default=str(score) if score is not None else None,
        show_default=False,
    )
    if value is not None:
        try:
            return parse_score(value)
        except ValueError:
            rich.print("[red]Invalid![/]")
            return ask_value(score)


def parse_score(value: str, /) -> Score | None:
    """
    Parse a score value from a string.
    """
    value = value.strip()
    if value == "":
        return None

    if value in SCORE_ALIASES:
        return SCORE_ALIASES[value]

    if value == "u":
        raise UndoOperation
    if value == "?":
        raise ShowHelp

    # Integral numbers != 1 are interpreted as percentages
    try:
        x = int(value)
    except ValueError:
        pass
    else:
        return score.MAX_SCORE * x / 100

    return score.parse_score(value)


class UndoOperation(Exception):
    pass


class ShowHelp(Exception):
    pass
