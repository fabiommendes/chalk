from __future__ import annotations

import csv
import datetime
import io
import json
from pathlib import Path
from typing import IO, Any, Collection, Literal, Sequence, assert_never, cast, overload

import rich
import yaml
from pydantic import BaseModel
from rich.syntax import Syntax

from .. import table as tb
from ..table import Table
from ..util.sequence import find_path

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
StructuredFormat = Literal["json", "yaml"]
SpreadsheetFormat = Literal["csv", "xlsx"]

VALID_YAML_TYPES = (
    str,
    int,
    float,
    bool,
    type(None),
    list,
    dict,
    datetime.datetime,
    datetime.date,
)


def load_spreadsheet(path: Path, columns: list[str] | None = None) -> Table[str | None]:
    """
    Load a spreadsheet file and return a list of dictionaries representing the rows.
    """
    data: list[dict[str, str | None]]

    if path.suffix == ".csv":
        with path.open() as f:
            reader = csv.DictReader(f)
            data = list(reader)
    elif path.suffix in [".xlsx", ".xls"]:
        raise NotImplementedError("Excel spreadsheet support is not implemented yet")
    elif path.suffix in [".json", ".yaml", ".yml"]:
        raw_data = load_structured_data(path)
        if not isinstance(raw_data, list):
            raise ValueError(f"Unsupported spreadsheet data: {path.suffix}")
        data = raw_data
    else:
        raise ValueError(f"Unsupported spreadsheet format: {path.suffix}")

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
        data = json.loads(path.read_text())
    elif path.suffix in [".yaml", ".yml"]:
        data = yaml.safe_load(path.read_text())
    else:
        raise ValueError(f"Unsupported structured data format: {path.suffix}")

    if not isinstance(data, (dict, list)):
        raise ValueError(f"Unsupported structured data type: {type(data).__name__}")
    return data


@overload
def dump_structured_data(
    data: Data,
    path: Path,
) -> None: ...


@overload
def dump_structured_data(
    data: Data,
    path: IO[str] | IO[bytes] | Path | None = None,
    format: StructuredFormat | None = None,
) -> None: ...


def dump_structured_data(
    data: Data,
    path: Any = None,
    format: StructuredFormat | None = None,
) -> None:
    """
    Save a dictionary or list to a structured json-like data file.
    """
    if format is None and isinstance(path, Path):
        format = validate_structured_format(path.suffix.removeprefix(".").lower())
    if isinstance(path, Path):
        path = path.open("w")  # automatically closes when function exit

    match (format, path):
        case ("json", None) | (None, None):
            rich.print_json(json.dumps(data, indent=2, default=json_default))
        case ("yaml", None):
            fd = io.StringIO()
            dump_structured_data(data, fd, format="yaml")
            src = fd.getvalue()
            rich.print(Syntax(src, "yaml"))
        case ("yaml", _):
            fd = io.StringIO()
            yaml_dump(data, fd)
            src = fd.getvalue()
            if not src.strip():
                raise ValueError("Failed to serialize data: empty output")
            path.write(src)  # Atomic write

        case ("json", _) | (None, _):
            fd = io.StringIO()
            json.dump(data, fd, indent=2, default=json_default)
            if not fd.getvalue().strip():
                raise ValueError("Failed to serialize data: empty output")
            path.write(fd.getvalue())  # Atomic write
        case other:
            assert_never(other)


def dump_spreadsheet(
    path: Path,
    data: Table[str | None],
    columns: list[str] | None = None,
    split_by: Collection[str] | None = None,
    keep: Sequence[str] | None = None,
) -> None:
    """
    Save a list of dictionaries representing rows to a spreadsheet file.
    """
    if not data:
        return

    if split_by is not None:
        for suffix in split_by:
            partial = data.select_columns(lambda k: k.endswith("." + suffix))
            if not partial:
                continue
            if keep:
                partial = tb.merge(
                    data.select_columns(keep),
                    partial,
                )
            partial_path = path.with_name(f"{path.stem}{suffix}{path.suffix}")
            dump_spreadsheet(partial_path, partial, columns=columns)
        return

    if path.suffix == ".csv":
        stream = io.StringIO()
        if columns is None:
            columns = list(data.iloc(0).keys())
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(data.to_dicts())

        # Atomic write to avoid data loss if the process is interrupted
        path.write_text(stream.getvalue())

    elif path.suffix in [".xlsx", ".xls"]:
        raise NotImplementedError("Excel spreadsheet support is not implemented yet")
    else:
        raise ValueError(f"Unsupported spreadsheet format: {path.suffix}")


def json_default(obj: Any) -> Any:  # -> str | list[Any]:
    """
    Handle additional types when serializing to JSON, such as Path objects.
    """
    if isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    elif isinstance(obj, Table):
        return obj.to_dicts()
    elif isinstance(obj, BaseModel):
        return obj.model_dump()

    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def validate_structured_format(format: str) -> StructuredFormat:
    """
    Validate that the given format is a supported structured data format.
    """
    if format in ["json", "yaml"]:
        return cast(StructuredFormat, format)
    else:
        msg = f"Unsupported data format: {format}, expect one of: json, yaml"
        raise ValueError(msg)


#
# Loaders and serializers
#
def string_representer(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    else:
        return dumper.represent_str(data)


yaml.SafeDumper.add_representer(str, string_representer)


#
# Default dumpers
#
def yaml_dump(data: Any, stream: IO[str]) -> None:
    try:
        yaml.safe_dump(
            data,
            stream,
            allow_unicode=True,
            encoding="utf-8",
            default_flow_style=False,
            sort_keys=False,
        )
    except yaml.YAMLError as e:

        def is_invalid_object(obj: Any) -> bool:
            return not isinstance(obj, VALID_YAML_TYPES)

        pair = find_path(is_invalid_object, data)
        if not pair:
            raise ValueError(e)

        path, invalid_obj = pair
        msg = f"Failed to serialize data to YAML: Unsupported object found at {path}: {invalid_obj!r}"
        raise ValueError(msg)
