from pathlib import Path
from typing import IO

import rich
from rich.syntax import Syntax

from . import serializers, validators
from .core import (
    SpreadsheetFormat,
    StructuredFormat,
    dump_spreadsheet,
    dump_structured_data,
    is_spreadsheet_format,
    is_structured_format,
    load_spreadsheet,
    load_structured_data,
    validate_spreadsheet_format,
    validate_structured_format,
)

__all__ = [
    "SpreadsheetFormat",
    "StructuredFormat",
    "dump_spreadsheet",
    "dump_structured_data",
    "load_spreadsheet",
    "load_structured_data",
    "validate_structured_format",
    "validate_spreadsheet_format",
    "serializers",
    "validators",
    "is_spreadsheet_format",
    "is_structured_format",
]


def dump_data(
    source: str | bytes,
    dest: IO[str] | IO[bytes] | Path | None = None,
    format: str | None = None,
    word_wrap: bool = False,
) -> None:
    """
    Dump data to a file or stdout in the specified format.
    """

    if dest is None and format:
        if isinstance(source, bytes):
            source = source.decode("utf-8")
        rich.print(Syntax(source, lexer=format, word_wrap=word_wrap))  # type: ignore (is Pyright crazy?)

    elif dest is None:
        if isinstance(source, bytes):
            source = source.decode("utf-8")
        print(source)

    elif isinstance(dest, Path) and isinstance(source, str):
        dest.write_text(source)

    elif isinstance(dest, Path) and isinstance(source, bytes):
        dest.write_bytes(source)

    elif hasattr(dest, "write"):
        # r2: issue/escrita-em-stream-nao-distingue-texto-de-bytes
        # TODO: can we tell IO[str] from IO[bytes] in runtime?
        dest.write(source)  # type: ignore
