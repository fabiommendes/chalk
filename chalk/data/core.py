from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import (
    IO,
    Any,
    Literal,
    Sequence,
    TypeIs,
    assert_never,
    cast,
    get_args,
    overload,
)

import rich
from rich.syntax import Syntax

from ..table import Table
from ..types import JSON
from ..util.path import write_text as _write_text
from . import json, yaml

__all__ = [
    "load_spreadsheet",
    "dump_spreadsheet",
    "load_structured_data",
    "dump_structured_data",
    "validate_structured_format",
    "StructuredFormat",
    "SpreadsheetFormat",
]

type Data = dict[str, Any] | list[Any]
type StructuredData = Data | JSON
type SpreadsheetData = list[dict[str, Any]]

StructuredFormat = Literal["json", "yaml"]
SpreadsheetFormat = Literal["csv", "json", "yaml"]

STRUCTURED_FORMAT_ALIASES: dict[str, StructuredFormat] = {"yml": "yaml"}
DEFAULT_BACKUPS: int | bool = False


def load_spreadsheet(path: Path, /, columns: list[str] | None = None) -> Table[str | None]:
    """
    Load a spreadsheet file and return a list of dictionaries representing the rows.
    """
    data: list[dict[str, str | None]]

    if path.suffix == ".csv":
        with path.open() as f:
            reader = csv.DictReader(f)
            data = list(reader)
    elif path.suffix in [".json", ".yaml", ".yml"]:
        raw_data = load_structured_data(path)
        if not isinstance(raw_data, list):
            raise ValueError(f"Unsupported spreadsheet data: {path.suffix}")
        data = raw_data
    else:
        raise ValueError(f"Unsupported spreadsheet format: {format}")

    for row in data:
        if not isinstance(row, dict):
            raise ValueError(f"Unsupported spreadsheet row: {row}")

        for key, value in row.items():
            if value == "":
                row[key] = None

    return Table(data, columns=columns)


def load_structured_data(path: Path) -> Data:
    """
    Load a structured json-like data file and return a dictionary or list representing the data.
    """
    data: Any
    if path.suffix == ".json":
        data = json.load(path.open())
    elif path.suffix in [".yaml", ".yml"]:
        data = yaml.load(path.open())
    else:
        raise ValueError(f"Unsupported structured data format: {path.suffix}")

    if not isinstance(data, (dict, list)):
        raise ValueError(f"Unsupported structured data type: {type(data).__name__}")
    return data


@overload
def dump_structured_data(
    data: StructuredData,
    path: Path,
    /,
    *,
    backup: bool | int = DEFAULT_BACKUPS,
) -> None: ...


@overload
def dump_structured_data(
    data: StructuredData,
    path: IO[str] | IO[bytes] | Path | None = None,
    /,
    *,
    format: StructuredFormat | None = None,
    backup: bool | int = DEFAULT_BACKUPS,
) -> None: ...


def dump_structured_data(
    data: StructuredData,
    path: IO[str] | IO[bytes] | Path | None = None,
    /,
    *,
    format: StructuredFormat | None = None,
    backup: bool | int = DEFAULT_BACKUPS,
) -> None:
    """
    Save a dictionary or list to a structured json-like data file.
    """

    if format is None and isinstance(path, Path):
        format = validate_structured_format(path.suffix.removeprefix(".").lower())

    if path is None:
        match format:
            case "json" | None:
                rich.print_json(json.dumps(data))
            case "yaml":
                fd = io.StringIO()
                dump_structured_data(data, fd, format="yaml")
                src = fd.getvalue()
                rich.print(Syntax(src, "yaml"))
            case _:
                assert_never(format)
        return

    match format:
        case "json" | None:
            src = json.dumps(data)
            if not src.strip():
                raise ValueError("Failed to serialize data: empty output")
            write_text(path, src, rotate=backup)

        case "yaml":
            src = yaml.dumps(data)
            if not src.strip():
                raise ValueError("Failed to serialize data: empty output")
            write_text(path, src, rotate=backup)

        case other:
            assert_never(other)


@overload
def dump_spreadsheet(
    data: Table[str | None] | Table[str],
    path: Path | IO[str] | IO[bytes] | None = None,
    /,
    *,
    format: SpreadsheetFormat | None = None,
    columns: list[str] | None = None,
    keep: Sequence[str] | None = None,
    backup: bool | int = DEFAULT_BACKUPS,
) -> None: ...


def dump_spreadsheet(
    data: Table[Any],
    path: Path | None | IO[str] | IO[bytes] = None,
    /,
    *,
    format: SpreadsheetFormat | None = None,
    columns: list[str] | None = None,
    keep: Sequence[str] | None = None,
    backup: bool | int = DEFAULT_BACKUPS,
) -> None:
    """
    Save a list of dictionaries representing rows to a spreadsheet file.
    """
    if not data:
        return

    if format is None and isinstance(path, Path):
        format = validate_spreadsheet_format(path.suffix.removeprefix(".").lower())

    if path is None and format == "csv":
        fd = io.StringIO()
        dump_spreadsheet(data, fd, columns=columns, backup=backup, format="csv")
        print(fd.getvalue())
        return

    match format:
        case "csv" | None:
            stream = io.StringIO()
            if columns is None:
                columns = ["id", *data.iloc(0).keys()]
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(data.to_dicts())

            # Atomic write to avoid data loss if the process is interrupted
            assert path is not None
            write_text(path, stream.getvalue(), rotate=backup)
        case "json" | "yaml":
            dump_structured_data(data.to_dicts(), path, format=format, backup=backup)
        case _:
            raise ValueError(f"Unsupported spreadsheet format: {format}")


def validate_structured_format(format: str) -> StructuredFormat:
    """
    Validate that the given format is a supported structured data format.
    """
    format = format.lower()
    if format in get_args(StructuredFormat):
        return cast(StructuredFormat, format)
    elif format in STRUCTURED_FORMAT_ALIASES:
        return STRUCTURED_FORMAT_ALIASES[format]
    else:
        msg = f"Unsupported data format: {format}, expect one of: json, yaml"
        raise ValueError(msg)


def is_structured_format(format: str) -> TypeIs[StructuredFormat]:
    """
    Check if the given format is a supported structured data format.
    """
    try:
        validate_structured_format(format)
        return True
    except ValueError:
        return False


def validate_spreadsheet_format(format: str) -> SpreadsheetFormat:
    """
    Validate that the given format is a supported spreadsheet data format.
    """
    if format in get_args(SpreadsheetFormat):
        return cast(SpreadsheetFormat, format)
    else:
        msg = f"Unsupported spreadsheet format: {format}, expect one of: csv, json, yaml"
        raise ValueError(msg)


def is_spreadsheet_format(format: str) -> TypeIs[SpreadsheetFormat]:
    """
    Check if the given format is a supported spreadsheet data format.
    """
    try:
        validate_spreadsheet_format(format)
        return True
    except ValueError:
        return False


def write_text(
    path: IO[str] | IO[bytes] | Path,
    data: str,
    *,
    encoding: str = "utf-8",
    rotate: int = 5,
) -> int:
    """
    Write text to a file or stream, with optional backup rotation for files.
    """
    if not data:
        raise ValueError(f"Trying to write empty data to {path}")

    if isinstance(path, Path):
        return _write_text(path, data, encoding=encoding, rotate=rotate)

    byte_stream = cast(IO[bytes], path)
    str_stream = cast(IO[str], path)

    def has_mode(obj: Any, mode: str) -> bool:
        return hasattr(obj, "mode") and isinstance(obj.mode, str) and mode in obj.mode

    if isinstance(path, io.TextIOBase) or not has_mode(path, "b"):
        return str_stream.write(data)

    if isinstance(path, io.RawIOBase | io.BufferedIOBase) or has_mode(path, "b"):
        return byte_stream.write(data.encode(encoding))

    # Fallback to string and then bytes writing
    try:
        return str_stream.write(data)
    except TypeError:
        pass

    try:
        return byte_stream.write(data.encode(encoding))
    except TypeError:
        pass
    raise TypeError(f"Unsupported path type: {type(path)}")
