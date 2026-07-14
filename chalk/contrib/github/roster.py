import csv
import difflib
from pathlib import Path
from typing import Annotated, Literal, Protocol

import rich
import typer

from ...cli.util import yn_prompt
from ...core import Classroom

app = typer.Typer()

Action = Literal["copy", "move", "link", "relink"]
type GithubId = str
type StudentId = str


class ActionFn(Protocol):
    def __call__(self, *, source: Path, dest: Path, force: bool = False) -> None: ...


@app.command(
    epilog="""
It assumes a .csv roster file generated with the columns: "identifier", 
"github_username", "name". The column "identifier" should match the student id 
in Chalk.

This is the same format used by github classroom when exporting a roster.
"""
)
def main(
    path: Annotated[
        Path,
        typer.Argument(
            metavar="PATH",
            help="Path to the roster file.",
        ),
    ] = Path("classroom_roster.csv"),
    verbose: Annotated[
        bool,
        typer.Option(
            ...,
            "-v",
            "--verbose",
            help="Print verbose output.",
        ),
    ] = False,
):
    """
    Update the student roster with the github usernames from data from the github classroom repositories.
    """
    if not path.exists():
        raise typer.BadParameter(f"Roster file {path} does not exist.")

    # Collect data
    id_to_name: dict[str, str] = {}
    id_to_github: dict[str, str] = {}

    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        columns = next(reader)

        for row in reader:
            entry = dict(zip(columns, row))
            id_to_name[entry["identifier"]] = entry["name"]
            id_to_github[entry["identifier"]] = entry["github_username"]

    github_to_id = {v: k for k, v in id_to_github.items()}

    # Try to match the github usernames with the student ids in Chalk
    cls = Classroom.load()
    roster = cls.get_roster()
    missing_github_ids: set[str] = set()
    saved_id_to_name: dict[str, str] = {}

    for student in roster.values():
        if (gh := student.github) is not None:
            if gh in github_to_id:
                gh_id = github_to_id.pop(gh)

                if gh_id != student.id:
                    msg = f"[cyan b]{gh}[/] is associated with [cyan b]{gh_id}[/], but in Chalk, the ID is [cyan b]{student.id}[/]."
                    rich.print(f"[yellow]Warning:[/yellow] {msg}")
                del id_to_name[gh_id]
                del id_to_github[gh_id]

        else:
            saved_id_to_name[student.id] = student.name
            missing_github_ids.add(student.id)

    # Now we remove all correct matches
    for id, github in list(id_to_github.items()):
        if id not in missing_github_ids:
            continue

        roster[id].github = github
        del id_to_name[id]
        del id_to_github[id]
        saved_id_to_name.pop(id, None)
        missing_github_ids.discard(id)

    # We find the names of missing students
    missing_names = {id: roster[id].name for id in missing_github_ids if id in roster}

    best_matches: dict[tuple[str, str], tuple[float, str, str]] = {}
    for id, name in missing_names.items():
        for gh_id, name_alt in id_to_name.items():
            gh = id_to_github[gh_id]
            ratio = difflib.SequenceMatcher(None, name.lower(), name_alt.lower()).ratio()
            if ratio > 0.5:
                best_matches[(id, gh)] = (ratio, name, name_alt)

    sorted_matches = sorted(best_matches.items(), key=lambda x: x[1], reverse=True)
    for (id, gh), (ratio, name, name_alt) in sorted_matches:
        # Was removed from a validated match
        if not (id in missing_names and gh in github_to_id):
            continue

        rich.print(f"[yellow]Potential match:[/yellow] [b]{id}/{gh}[/]")
        rich.print(f"  [b]chalk: [/] [green]{name}[/]")
        rich.print(f"  [b]github:[/] [cyan]{name_alt}[/]")
        if yn_prompt("Accept this match?", default="y"):
            roster[id].github = gh

            missing_names.pop(id, None)
            missing_github_ids.discard(id)

            gh_id = github_to_id.pop(gh)
            id_to_name.pop(gh_id, None)
            id_to_github.pop(gh_id, None)

    if id_to_github:
        rich.print("\nThe following github usernames could not be matched:")
        for id, gh in id_to_github.items():
            name = id_to_name.get(id) or "<unknown>"
            rich.print(f"  [b yellow]{gh}[/]: {name}")

    if missing_names and verbose:
        rich.print("\bThe following students are missing github usernames:")
        for id, name in sorted(missing_names.items()):
            rich.print(f"  [b yellow]{id}[/]: {name}")
    elif missing_names:
        rich.print(f"Missing github usernames for {len(missing_names)} students:")

    roster.save()


if __name__ == "__main__":
    app()
