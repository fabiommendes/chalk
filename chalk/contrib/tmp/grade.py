from collections import defaultdict
from decimal import Decimal
from typing import Annotated, cast

import rich
import typer
from rich.prompt import Prompt

from ...core import AnyAnswer, Question
from ...info import Classroom

app = typer.Typer()


@app.command()
def main(
    quiz_id: Annotated[
        str | None,
        typer.Argument(
            metavar="ASSIGNMENT",
            help="Quiz id",
        ),
    ] = None,
    question_id: Annotated[
        str | None,
        typer.Argument(
            metavar="QUESTION",
            help="Question id",
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
):
    """
    Simple manual grader
    """

    cls, quiz, question = Classroom.from_prompt(quiz_id=quiz_id, question_id=question_id)
    responses = dict(quiz.submissions.iter_answers(question=question))

    by_answer: dict[str, list[AnyAnswer]] = defaultdict(list)
    for response in responses.values():
        if not force or response.grade is None:
            by_answer[cast(str, response.answer)].append(response)

    msg = f"Found [blue]{len(responses)}[/] responses for question [bold blue]{question_id}[/]"
    rich.print(msg)

    for answer, responses in by_answer.items():
        question.render_answer(answer)
        rich.print(f"Found [blue]{len(responses)}[/] responses for this answer.")

        grade = get_score(question)

        feedback = None
        if grade != question.score:
            feedback = Prompt.ask("Feedback (optional)", default="") or None

        for response in responses:
            response.score = grade
            response.feedback = feedback

    quiz.save()


def get_score(question: Question) -> Decimal:
    max_grade = question.score or Decimal(1)
    try:
        value = Decimal(Prompt.ask(f"Grade (0-{max_grade})", default=str(max_grade)))
    except Exception:
        return get_score(question)

    if not 0 <= value <= max_grade:
        rich.print(f"[red]Grade must be between 0 and {max_grade}[/]")
        return get_score(question)

    return value


if __name__ == "__main__":
    app()
