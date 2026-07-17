import csv
import shutil
from functools import wraps
from pathlib import Path
from typing import Annotated, Counter, Literal, Protocol, assert_never

import rich
import typer

app = typer.Typer()

Action = Literal["copy", "move", "link", "relink"]
type GithubId = str
type StudentId = str


class ActionFn(Protocol):
    def __call__(self, *, source: Path, dest: Path, force: bool = False) -> None: ...


@app.command()
def main(
    source: Annotated[
        Path | None,
        typer.Argument(
            ...,
            metavar="PATH",
            help="Path to github classroom repositories.\nUsually produced by the `gh classroom clone student-repos` command.",
        ),
    ] = None,
    roster: Annotated[
        Path,
        typer.Option(
            ...,
            "--roster",
            "-r",
            metavar="PATH",
            help="Path to the roster file.",
        ),
    ] = Path("classroom_roster.csv"),
    output: Annotated[
        Path,
        typer.Option(
            ...,
            "--output",
            "-o",
            metavar="PATH",
            help="Path to the output directory.",
        ),
    ] = Path("repos"),
    action: Annotated[
        Action,
        typer.Option(
            ...,
            "--action",
            "-a",
            help="Action to perform on the repositories.\n\n"
            " - copy: Copy the repositories to the output directory.\n\n"
            " - move: Move the repositories to the output directory.\n\n"
            " - link: Create symbolic links to the repositories in the output directory.\n\n"
            " - relink: Update existing symbolic links to point to the repositories in the output directory.",
        ),
    ] = "copy",
    force: Annotated[
        bool,
        typer.Option(
            ...,
            "--force",
            "-f",
            help="Force the action even if the output directory already exists.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            ...,
            "--verbose",
            "-v",
            help="Suppress debug messages.",
        ),
    ] = False,
):
    """
    Extract data from github classroom repositories.
    """
    # Infer input path, if needed
    if source is None:
        match list(Path().glob("*-submissions")):
            case []:
                typer.echo("No github classroom repositories found.", err=True)
                raise typer.Exit(code=1)
            case [single]:
                source = single
            case _:
                msg = "Multiple github classroom repositories found. Please specify the path to the repositories."
                typer.echo(msg, err=True)
                raise typer.Exit(code=1)
    source = source.resolve()

    # Collect roster entries. Assume the identifier column is the StudentId
    gh_to_student_id: dict[GithubId, StudentId] = {}
    has_submited: set[StudentId] = set()
    not_in_roster: set[GithubId] = set()

    try:
        with open(roster, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                github_id = row["github_username"]
                gh_to_student_id[github_id] = row["identifier"]
    except FileNotFoundError:
        typer.echo(f"Roster file not found: {roster}", err=True)
        raise typer.Exit(code=1)

    # Process each student in the roster
    action_fn = get_action(action)
    prefix, gh_usernames = extract_repo_info(source)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    for gh_username in gh_usernames:
        student_id = gh_to_student_id.get(gh_username)
        if student_id is None:
            not_in_roster.add(gh_username)
            continue

        action_fn(
            source=source / f"{prefix}-{gh_username}",
            dest=output / student_id,
            force=force,
        )
        has_submited.add(student_id)

    if verbose and not_in_roster:
        msg = "".join(sorted(f"\n  - [dim white]{x}[/]" for x in not_in_roster))
        msg = f"[bold white on red]Warning:[/] Usernames were not linked: {msg}"
        rich.print(msg)

    unprocessed = set(gh_to_student_id.values()) - has_submited
    if verbose and unprocessed:
        msg = "".join(sorted(f"\n  - [dim white]{x}[/]" for x in unprocessed))
        msg = f"[bold white on red]Warning:[/] The following usernames were not found in the repositories: {msg}"
        rich.print(msg)


#
# Utility functions
#
def extract_repo_info(source: Path, /) -> tuple[str, set[GithubId]]:
    """
    Extract the prefix and usernames from the output directory.
    """
    if not source.exists():
        typer.echo(f"Output directory does not exist: {source}", err=True)
        raise typer.Exit(code=1)
    elif not source.is_dir():
        typer.echo(f"Output path is not a directory: {source}", err=True)
        raise typer.Exit(code=1)

    prefixes: Counter[str] = Counter()
    names: set[str] = set()

    for path in source.iterdir():
        name = path.name
        if path.is_dir() or path.resolve().is_dir() and "-" in name:
            names.add(name)
            *parts, _ = name.split("-")
            for i in range(len(parts)):
                prefix = "-".join(parts[: i + 1])
                prefixes[prefix] += 1

    if not prefixes:
        typer.echo(f"No github classroom repositories found in {source}.", err=True)
        raise typer.Exit(code=1)

    _, _, prefix = max(map(lambda p: (p[1], len(p[0]), p[0]), prefixes.most_common()))
    return prefix, {
        name.removeprefix(f"{prefix}-") for name in names if name.startswith(f"{prefix}-")
    }


#
# Actions
#
def get_action(action: Action, /) -> ActionFn:
    match action:
        case "copy":
            return action_copy
        case "move":
            return action_move
        case "link":
            return action_link
        case "relink":
            return action_relink
        case other:
            assert_never(other)


def clean_before(fn: ActionFn, /) -> ActionFn:
    @wraps(fn)
    def wrapper(*, source: Path, dest: Path, force: bool = False) -> None:
        if dest.exists() and not force:
            return
        if dest.exists() and dest.is_symlink():
            dest.unlink()
        elif dest.exists() and dest.is_dir():
            shutil.rmtree(dest)

        fn(source=source, dest=dest, force=force)

    return wrapper


@clean_before
def action_copy(*, source: Path, dest: Path, force: bool = False) -> None:
    shutil.copytree(source, dest)


@clean_before
def action_move(*, source: Path, dest: Path, force: bool = False) -> None:
    shutil.move(source, dest)


@clean_before
def action_link(*, source: Path, dest: Path, force: bool = False) -> None:
    dest.symlink_to(source, target_is_directory=True)


@clean_before
def action_relink(*, source: Path, dest: Path, force: bool = False) -> None:
    dest.symlink_to(source.relative_to(dest.parent, walk_up=True), target_is_directory=True)


if __name__ == "__main__":
    app()
