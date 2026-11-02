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
    quiz_id: Annotated[
        str,
        typer.Argument(
            ...,
            metavar="ASSIGNMENT",
            help="Quiz identifier (e.g. 'hw1', 'exam1', etc.)",
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
    timeout: Annotated[
        float,
        typer.Option(
            ...,
            "-t",
            "--timeout",
            metavar="SECONDS",
            help="Timeout for the autograder script (in seconds)",
        ),
    ] = DEFAULT_TIMEOUT,
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
    keep_files: Annotated[
        bool,
        typer.Option(
            ...,
            "-k",
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
            help="Limit the number of students to grade per batch",
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
    run_script: Annotated[
        bool,
        typer.Option(
            ...,
            "-r",
            "--run-script",
            help="Only run the autograder script without saving grades or feedback",
        ),
    ] = False,
    run: Annotated[
        bool,
        typer.Option(
            ...,
            "--run",
            help="Only run the script and do not save grades or feedback.",
        ),
    ] = False,
) -> None:
    """
    Run the autograder for the specified quiz and question.
    """

    cls = Classroom.load()
    quiz = cls.get_quiz(quiz_id)
    if quiz is None:
        raise typer.BadParameter(f"Quiz '{quiz_id}' not found.")

    if student_id is not None:
        students = [cls.prompt_student(student_id, fuzzy=True)]
    else:
        students = [*cls.roster.values()]
        if limit is not None and 0 < limit < len(students):
            students = students[:limit]

    if run_script:
        question = cls.prompt_question(quiz, question_id)
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
            capture_output=not run,
        )

    else:
        question = cls.prompt_question(quiz, question_id)
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


#
# Simple script runner
#
def run_autograder_debug(
    question: Question,
    students: list[Student],
    keep_files: bool,
    verbose: bool,
    timeout: float,
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
    timeout: float = DEFAULT_TIMEOUT,
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
        elif score is not None and graded.score != score:
            if is_score(score):
                rich.print(rich_render_percent(score), end=" -> ")
            else:
                rich.print(score, end=" -> ")
            show(graded)
            continue
        else:
            show(graded)

        has_changed = True
        grades.set_score(
            graded.score,
            student=student,
            question=question,
            feedback=graded.feedback,
            adjustments=graded.adjustments,
        )
        if has_changed and not dry_run:
            grades.save()
