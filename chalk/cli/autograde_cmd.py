from __future__ import annotations

import shutil
from functools import partial
from pathlib import Path
from typing import Annotated, Any

import rich
import typer
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from ..core import Classroom, Question, Student
from ..core.grader import DEFAULT_TIMEOUT, Grader, GraderKwargs, is_score
from ..core.score import rich_render_percent
from ..question import render_answer
from .util import (
    safe,
    yn_prompt,
)


def add_autograde_command(app: typer.Typer) -> None:
    app.command(no_args_is_help=False)(autograde)


@safe
def autograde(
    loc: Annotated[
        str,
        typer.Argument(
            ...,
            metavar="LOC",
            help="Quiz/question (e.g. 'p1/q1'). With only the quiz, asks for the question.",
        ),
    ],
    timeout: Annotated[
        float | None,
        typer.Option(
            ...,
            "--timeout",
            metavar="SECONDS",
            help=(
                "Timeout for the autograder script (in seconds). Defaults to "
                f"autograder.timeout in conf.yaml, or {DEFAULT_TIMEOUT:g}."
            ),
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
            "-n",
            "--dry-run",
            help="Simulate the grading process without making any changes to grades or feedback",
        ),
    ] = False,
    keep_files: Annotated[
        bool,
        typer.Option(
            ...,
            "--keep-files",
            help="Keep temporary files generated during grading (for debugging)",
        ),
    ] = False,
    keep_failed: Annotated[
        bool,
        typer.Option(
            ...,
            "--keep-failed",
            help="Keep temporary files when autograder script exits with an error (for debugging)",
        ),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option(
            ...,
            "--limit",
            metavar="N",
            help="Grade only the first N students of the roster",
        ),
    ] = None,
    force_grading: Annotated[
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
    verbose: Annotated[
        bool,
        typer.Option(
            ...,
            "-v",
            "--verbose",
            help="Show detailed output during the grading process",
        ),
    ] = False,
    run: Annotated[
        bool,
        typer.Option(
            ...,
            "--run",
            help="Run the autograder for each student and show its output. Saves nothing.",
        ),
    ] = False,
    check: Annotated[
        bool,
        typer.Option(
            ...,
            "--check",
            help=(
                "Grade the reference solution of the question and fail unless it gets "
                "the full score. Nothing is saved."
            ),
        ),
    ] = False,
) -> None:
    """
    Run the autograder for the specified quiz and question.
    """

    cls, quiz, question = Classroom.from_prompt(loc, check_exist=True)
    if question is None:
        question = cls.prompt_question(quiz, None)

    if student_id is not None:
        students = [cls.prompt_student(student_id, fuzzy=True)]
    else:
        students = [*cls.roster.values()]
        if limit is not None and 0 < limit < len(students):
            students = students[:limit]

    if check:
        check_autograder(question, timeout=timeout, keep_files=keep_files)
        return

    if run:
        if sort:
            raise typer.BadParameter("There is nothing to sort", param_hint=["--sort", "-s"])
        if output_format:
            raise typer.BadParameter("There is nothing to format", param_hint=["--format", "-f"])
        if output_path:
            raise typer.BadParameter("There is no output to save", param_hint=["--output", "-o"])

        run_autograder_debug(
            question,
            students=students,
            keep_files=keep_files,
            verbose=verbose,
            timeout=timeout,
        )

    else:
        run_autograder(
            question,
            students=students,
            keep_files=keep_files,
            verbose=verbose,
            timeout=timeout,
            sort=sort,
            output_format=output_format,
            output_path=output_path,
            auto_yes=auto_yes,
            keep_failed=keep_failed,
            force_grading=force_grading,
            dry_run=dry_run,
        )


def check_autograder(question: Question, *, timeout: float | None, keep_files: bool) -> None:
    """
    Grade the reference answer of the question and exit with code 1 unless it
    gets the full score.
    """
    grader = question.get_grader()
    if grader is None:
        raise typer.BadParameter("Question does not use an autograder.", param_hint="QUESTION")
    answer = question.get_reference_answer()
    if answer is None:
        msg = "Question has no reference solution (solution/ or answer_key.*)."
        raise typer.BadParameter(msg, param_hint="QUESTION")

    graded = grader("solution", answer, timeout=timeout, keep_failed=True, keep_files=keep_files)
    if graded is None:
        rich.print("[red]The reference solution was not graded.[/]")
        raise typer.Exit(1)

    rich.print(f"Reference solution: {graded}")
    if graded.feedback:
        rich.print(Panel(graded.feedback, title="Feedback", expand=False))
    if graded.notes:
        rich.print(Panel(graded.notes, title="Notes", expand=False, style="yellow"))
    if not is_score(graded.score) or graded.score < 1:
        rich.print("[red]The reference solution does not get the full score.[/]")
        raise typer.Exit(1)


#
# Simple script runner
#
def run_autograder_debug(
    question: Question,
    students: list[Student],
    keep_files: bool,
    verbose: bool,
    timeout: float | None,
    capture_output: bool = True,
) -> None:
    grader: Grader[Any] | None = question.get_grader()
    yn_default = "n"

    if grader is None:
        rich.print("[dim]This question does not use an autograder script.[/]")
        exit(1)

    for student in students:
        answer = question.quiz.submissions.get_answer(student=student, question=question)
        if answer is None:
            continue

        if (
            verbose
            or yn_default != "never"
            and (
                yn_default := Prompt.ask(
                    "Show student answer?",
                    choices=["y", "n", "never"],
                    default=yn_default,
                )
            )
            == "y"
        ):
            panel = Panel(
                render_answer(question, answer),
                title=f"Student {student.id} answer",
                expand=False,
            )
            rich.print(panel)

        width = shutil.get_terminal_size().columns
        rich.print(Text("─" * width, style="dim"))
        result = grader(
            student.id,
            answer,
            keep_files=keep_files,
            on_output_line=print,
            timeout=timeout,
            capture_output=capture_output,
        )
        rich.print(Text("─" * width, style="dim"))
        rich.print(f"[dim]Result for student {student.id}: {result or 'not-graded'}[/]")

        print()
        if yn_prompt("Continue to next student?", "y") is False:
            break


def run_autograder(
    question: Question,
    *,
    students: list[Student] | None = None,
    keep_files: bool = False,
    verbose: bool = False,
    timeout: float | None = None,
    sort: str | None = None,
    output_format: str | None = None,
    output_path: Path | None = None,
    auto_yes: bool = False,
    keep_failed: bool = False,
    force_grading: bool = False,
    dry_run: bool = False,
):
    # Verbose level:
    #   0 = no output, except final output
    #   1 = summary
    #   2 = detailed
    verbose_level = 0
    if output_path is not None or output_format is None:
        verbose_level = 1
    if verbose:
        verbose_level = 2

    def log_message(obj: Any, *, level: int, style: str | None = None) -> None:
        if level > verbose_level:
            return
        if style:
            obj = Text(str(obj), style=style)
        rich.print(obj)

    info = partial(log_message, level=2)
    show = partial(log_message, level=1)

    grader = question.get_grader()
    if grader is None:
        raise typer.BadParameter(
            "Question does not use an autograder script.",
            param_hint="QUESTION",
        )
    grader_kwargs: GraderKwargs = {
        "timeout": timeout,
        "keep_files": keep_files,
        "keep_failed": keep_failed,
    }

    if students is None:
        students = [*question.quiz.classroom.roster.values()]

    grades = question.quiz.grades
    submissions = question.quiz.submissions
    has_changed = False

    for student in students:
        score = grades.get_score(student=student, question=question)
        answer = submissions.get_answer(student=student, question=question)
        if answer is None:
            continue

        rich.print(f"* [b cyan]{student.id}:[/]", end=" ")
        if score is not None and not force_grading:
            info(f"already graded ({score})", style="dim")
            continue

        ans: Any = question.validate_answer(answer)
        graded = grader(student.id, ans, **grader_kwargs)
        if graded is None:
            show("not graded.", style="yellow")
            continue
        if score is not None and graded.score != score:
            if is_score(score):
                rich.print(rich_render_percent(score), end=" -> ")
            else:
                rich.print(score, end=" -> ")
        show(graded)
        if graded.notes:
            rich.print(Panel(graded.notes, title=f"Notes on {student.id}", style="yellow"))

        has_changed = True
        grades.set_score(
            graded.score,
            student=student,
            question=question,
            feedback=graded.feedback,
            notes=graded.notes,
        )
        if has_changed and not dry_run:
            grades.save()
