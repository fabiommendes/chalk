from typing import Annotated, Mapping

import rich
import typer
from plagiarism.pairwise import Match, Pairwise, tokens
from rich.prompt import Prompt
from rich.table import Table

from ..core import StudentId
from .util import safe

app = typer.Typer(help="Manage questions in quizzes.", no_args_is_help=True)


# ==============================================================================
# chalk plagiarism scan ASSIGNMENT QUESTION
# ==============================================================================
@app.command()
@safe
def scan(
    quiz_id: Annotated[
        str | None,
        typer.Argument(
            ...,
            metavar="ASSIGNMENT",
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
) -> None:
    """
    Scan for plagiarism in the given quiz and question.
    """
    _, question, responses = read_quiz_question_and_responses(
        quiz_id, question_id, validate=True, skip_empty=True
    )

    if question.answer_to_text is None:
        msg = f"Plagiarism detection is not supported for {question.type} questions."
        typer.echo(msg)
        exit(1)

    data: dict[StudentId, str] = {
        k: question.answer_to_text(r.answer) for k, r in responses.items() if r.answer is not None
    }

    pw = Pairwise(data, tokens, threshold=0.9)
    start = "ask"
    for m in pw.iter_similar():
        ctrl = MatchInteract(m, start=start)
        try:
            start = ctrl.run()
        except StopIteration:
            break


def yn_prompt(prompt: str, default: bool = True) -> bool:
    """
    Prompt the user for a yes/no answer.

    Returns True for yes and False for no.
    """
    default_str = "y" if default else "n"
    answer = Prompt.ask(prompt, choices=["y", "n"], default=default_str, show_choices=True)
    return answer == "y"


def pause() -> None:
    """
    Pause the program until the user presses enter.
    """
    Prompt.ask("Press [enter] to continue", default="", show_default=False)


class MatchInteract:
    def __init__(self, match: Match[str, str], start: str = "ask") -> None:
        self.match = match
        self.state = start

    def run(self) -> str:
        msg = (
            f"[b yellow]{self.match.id_a} <-> {self.match.id_b}[/]: [red]{self.match.score:.2f}[/]"
        )
        rich.print(msg)

        ask = self.state == "ask"

        while True:
            state = self.state
            if ask:
                state = multi_prompt(
                    "Select an action",
                    {
                        "next": "Continue to the next match",
                        "stop": "Stop scanning",
                        "diff": "Show the diff between the two responses",
                        "a": f"Show response for {self.match.id_a}",
                        "b": f"Show response for {self.match.id_b}",
                        "ab": "Show response side by side",
                    },
                )
            ask = True

            match state:
                case "next":
                    return self.state
                case "stop":
                    raise StopIteration
                case "diff":
                    for line in self.match.diff():
                        rich.print(line, end="")
                    print("\n")
                    self.state = "diff"
                case "a":
                    rich.print(f"[b yellow]{self.match.id_a}[/]:")
                    rich.print(self.match.a, end="\n\n")
                    self.state = "a"
                case "b":
                    rich.print(f"[b yellow]{self.match.id_b}[/]:")
                    rich.print(self.match.b, end="\n\n")
                    self.state = "b"
                case "ab":
                    table = Table(show_header=True, header_style="bold magenta")
                    table.add_column(self.match.id_a, style="dim")
                    table.add_column(self.match.id_b, style="dim")
                    table.add_row(self.match.a, self.match.b)
                    rich.print(table)
                    self.state = "ab"


def multi_prompt(prompt: str, choices: Mapping[str, str]) -> str:
    """
    Prompt the user for multiple choices.

    Returns a list of selected choices.
    """

    choice_list = list(choices)
    rich.print(f"[b]{prompt}[/]")
    for i, c in enumerate(choice_list):
        rich.print(f"  [b yellow]{i + 1}.[/] {choices[c]}")
    result = Prompt.ask(
        "Options",
        choices=list(map(str, range(1, len(choice_list) + 1))),
        show_choices=False,
        default="1",
    )
    return choice_list[int(result) - 1]
