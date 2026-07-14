from collections import defaultdict
from decimal import Decimal
from typing import Annotated, cast

import rich
import typer
from rich.prompt import Prompt

from ...core import Grade, Question, Quiz

app = typer.Typer()


@app.command()
def main(
    quiz_id: Annotated[
        str,
        typer.Argument(
            metavar="ASSIGNMENT",
            help="Quiz id",
        ),
    ],
    question_id: Annotated[
        str,
        typer.Argument(
            metavar="QUESTION",
            help="Question id",
        ),
    ],
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force regrading even if responses already have grades",
        ),
    ] = False,
):
    """
    Simple manual grader
    """
    try:
        quiz = Quiz.load(id=quiz_id)
    except FileNotFoundError:
        raise typer.BadParameter(f"Quiz {quiz_id} does not exist.")

    question = quiz.get_question(question_id)
    if question is None:
        raise typer.BadParameter(f"Question {question_id} does not exist in quiz {quiz_id}.")

    responses = quiz.get_responses_for_question(question_id, skip_empty=True)

    by_answer: dict[str, list[Response]] = defaultdict(list)
    for response in responses.values():
        if not force or response.grade is None:
            by_answer[cast(str, response.answer)].append(response)

    msg = f"Found [blue]{len(responses)}[/] responses for question [bold blue]{question_id}[/]"
    rich.print(msg)

    for answer, responses in by_answer.items():
        question.display_answer(answer)
        rich.print(f"Found [blue]{len(responses)}[/] responses for this answer.")

        grade = get_grade(question)

        feedback = None
        if grade != question.grade:
            feedback = Prompt.ask("Feedback (optional)", default="") or None

        for response in responses:
            response.grade = Grade(grade)
            response.feedback = feedback

    quiz.save()


def get_grade(question: Question) -> Decimal:
    max_grade = question.grade or Decimal(1)
    try:
        value = Decimal(Prompt.ask(f"Grade (0-{max_grade})", default=str(max_grade)))
    except Exception:
        return get_grade(question)

    if not 0 <= value <= max_grade:
        rich.print(f"[red]Grade must be between 0 and {max_grade}[/]")
        return get_grade(question)

    return value


if __name__ == "__main__":
    app()
