import csv
import datetime
import json
from pathlib import Path

import yaml

from .util import merge_columns, select_columns


def load_spreadsheet(path: Path) -> list[dict[str, str | None]]:
    """
    Load a spreadsheet file and return a list of dictionaries representing the rows.
    """
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
        for key, value in row.items():
            if value == "":
                row[key] = None
    return data


def load_structured_data(path: Path) -> dict | list:
    """
    Load a structured json-like data file and return a dictionary or list representing the data.
    """
    if path.suffix == ".json":
        return json.loads(path.read_text())
    elif path.suffix in [".yaml", ".yml"]:
        return yaml.safe_load(path.read_text())
    else:
        raise ValueError(f"Unsupported structured data format: {path.suffix}")


def save_structured_data(path: Path, data: dict | list):
    """
    Save a dictionary or list to a structured json-like data file.
    """
    if path.suffix == ".json":
        path.write_text(json.dumps(data, indent=2, default=json_default))
    elif path.suffix in [".yaml", ".yml"]:
        path.write_text(yaml.safe_dump(data))
    else:
        raise ValueError(f"Unsupported structured data format: {path.suffix}")


def save_spreadsheet(
    path: Path,
    data: list[dict[str, str | None]],
    columns: list[str] | None = None,
    split_by: list[str] | None = None,
    keep: set[str] | None = None,
):
    """
    Save a list of dictionaries representing rows to a spreadsheet file.
    """
    if not data:
        return

    if split_by is not None:
        for suffix in split_by:
            partial = select_columns(data, lambda k: k.endswith("/" + suffix))
            if not partial[0]:
                continue
            if keep:
                partial = merge_columns(
                    select_columns(data, keep),
                    partial,
                )
            partial_path = path.with_name(f"{path.stem}{suffix}{path.suffix}")
            save_spreadsheet(partial_path, partial, columns=columns)
        return

    if path.suffix == ".csv":
        with path.open("w", newline="") as f:
            if columns is None:
                columns = list(data[0].keys())
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(data)
    elif path.suffix in [".xlsx", ".xls"]:
        raise NotImplementedError("Excel spreadsheet support is not implemented yet")
    else:
        raise ValueError(f"Unsupported spreadsheet format: {path.suffix}")


def json_default(obj):
    """
    Handle additional types when serializing to JSON, such as Path objects.
    """
    if isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()

    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
