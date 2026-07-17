import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zipfile import Path

from frozendict import frozendict
from pydantic import BaseModel

from ..table import Table
from . import serializers as s


def load(fp: Any, /) -> Any:
    try:
        return json.load(fp)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to load JSON data: {e}") from e


def loads(s: str, /) -> Any:
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to load JSON data: {e}") from e


def dumps(data: Any, /, *, indent: int = 2) -> str:
    return json.dumps(data, indent=indent, default=json_default)


def dump(data: Any, fp: Any, /, *, indent: int = 2) -> None:
    json.dump(data, fp, indent=indent, default=json_default)


def json_default(obj: Any) -> Any:  # -> str | list[Any]:
    """
    Handle additional types when serializing to JSON, such as Path objects.
    """
    if isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, Table):
        return obj.to_dicts()
    elif isinstance(obj, Decimal):
        return s.decimal(obj)
    elif isinstance(obj, BaseModel):
        return obj.model_dump()
    elif isinstance(obj, frozendict):
        return dict(obj)
    elif isinstance(obj, tuple):
        return list(obj)

    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
