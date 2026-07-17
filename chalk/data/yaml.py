from __future__ import annotations

import datetime
import io
from decimal import Decimal
from typing import IO, Any

import yaml
from frozendict import frozendict

from ..util.sequence import find_path
from . import serializers as s

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


def load(stream: IO[str], /) -> Any:
    try:
        return yaml.safe_load(stream)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to load YAML data: {e}") from e


def loads(s: str, /) -> Any:
    try:
        return yaml.safe_load(s)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to load YAML data: {e}") from e


def dump(data: Any, stream: IO[str], /, *, indent: int = 2) -> None:
    try:
        yaml.dump(
            data,
            stream,
            indent=indent,
            allow_unicode=True,
            encoding="utf-8",
            default_flow_style=False,
            sort_keys=False,
            Dumper=SafeDumper,
        )
    except yaml.YAMLError as e:

        def is_invalid_object(obj: Any) -> bool:
            return not isinstance(obj, VALID_YAML_TYPES)

        pair = find_path(is_invalid_object, data)
        if not pair:
            raise ValueError(e)

        path, invalid_obj = pair
        msg = (
            f"Failed to serialize data to YAML: Unsupported object found at {path}: {invalid_obj!r}"
        )
        raise ValueError(msg)


def dumps(data: Any, /, *, indent: int = 2) -> str:
    """
    Serialize a Python object to a YAML-formatted string.
    """
    fd = io.StringIO()
    dump(data, fd, indent=indent)
    return fd.getvalue()


#
# Default dumpers
#
class SafeDumper(yaml.SafeDumper):
    """
    A custom YAML SafeDumper that handles additional types like Decimal and multi-line strings.
    """


def string_representer(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    else:
        return dumper.represent_str(data)


def decimal_representer(dumper: yaml.SafeDumper, data: Decimal) -> yaml.Node:
    value = s.decimal(data)
    if isinstance(value, str):
        return string_representer(dumper, value)
    elif isinstance(value, int):
        return dumper.represent_int(value)
    elif isinstance(value, float):
        return dumper.represent_float(value)
    else:
        raise ValueError(f"Cannot represent Decimal {data} as YAML: {value!r}")


def frozendict_representer(dumper: yaml.SafeDumper, data: frozendict) -> yaml.Node:
    return dumper.represent_dict(dict(data))


SafeDumper.add_representer(str, string_representer)
SafeDumper.add_representer(Decimal, decimal_representer)
SafeDumper.add_representer(frozendict, frozendict_representer)
