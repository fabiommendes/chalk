from pathlib import Path
from typing import Annotated, Literal

import errorz as rz
import typer

from chalk.data import (
    dump_spreadsheet,
    dump_structured_data,
    load_spreadsheet,
    load_structured_data,
    validate_spreadsheet_format,
    validate_structured_format,
)

from ...table import Table
from ...types import JSON

app = typer.Typer()

Action = Literal["copy", "move", "link", "relink"]
GithubId = str
StudentId = str


@app.command()
def main(
    source: Annotated[
        Path,
        typer.Argument(
            ...,
            metavar="FROM",
            help="Input data file",
        ),
    ],
    destination: Annotated[
        Path,
        typer.Argument(
            ...,
            metavar="TO",
            help="Output data file.",
        ),
    ],
    force: Annotated[
        bool,
        typer.Option(
            ...,
            "--force",
            "-f",
            help="Overwrite target, if it exists.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            ...,
            "--dry-run",
            "-d",
            help="Perform a trial run with no changes made.",
        ),
    ] = False,
) -> None:
    """
    Convert file between accepted formats.

    It can convert between CSV, JSON, YAML, TOML and Excel formats.
    """
    source_data = load(source)
    if not dry_run and destination.exists() and not force:
        raise FileExistsError(f"Destination file already exists: {destination}")

    dump(source_data, None if dry_run else destination, format=destination.suffix.lstrip("."))


def load(path: Path) -> JSON:
    if not path.exists():
        raise FileNotFoundError(path)

    fmt = path.suffix.lstrip(".")

    if not rz.is_err(rz.call(validate_spreadsheet_format, fmt)):
        table = load_spreadsheet(path)
        return table.to_dicts()

    if not rz.is_err(rz.call(validate_structured_format, fmt)):
        data = load_structured_data(path)
        return data

    raise ValueError(f"Unsupported file format: {path.suffix}")


def dump(data: JSON, path: Path | None, format: str) -> None:
    if not rz.is_err(sheet_fmt := rz.call(validate_spreadsheet_format, format)):
        table: Table[str | None] = Table(data)  # type: ignore
        dump_spreadsheet(table, path, format=sheet_fmt)
        return

    if not rz.is_err(st_fmt := rz.call(validate_structured_format, format)):
        dump_structured_data(data, path, format=st_fmt)
        return

    raise ValueError(f"Unsupported file format: {format}")


if __name__ == "__main__":
    app()
