import builtins
import re
from decimal import Decimal
from enum import Enum
from typing import Any, Callable

type Validator[T] = Callable[[Any], T]

TEXT_FORMAT_ALIAS = {
    "plain": "text",
    "plain-text": "text",
    "md": "markdown",
    "py": "python",
    "js": "javascript",
    "c++": "cpp",
    "c#": "csharp",
}


def optional[T](fn: Validator[T], /) -> Validator[T | None]:
    """
    A helper function to create a validator for an optional field.
    """

    def optional_validator(value: T | None) -> Any:
        if value is None:
            return None
        return fn(value)

    optional_validator.__name__ = f"optional_{getattr(fn, '__name__', 'serializer')}"
    return optional_validator


def list[T](fn: Validator[T], /) -> Validator[builtins.list[T]]:
    """
    A helper function to create a validator for a list of items.
    """

    def list_validator(values: builtins.list[T]) -> Any:
        if isinstance(values, (str, bytes)):
            raise ValueError(f"Expected an iterable, got {type(values).__name__}")
        try:
            values_iter = iter(values)
        except TypeError:
            raise ValueError("Expected an iterable")
        return [fn(value) for value in values_iter]

    list_validator.__name__ = f"list_{getattr(fn, '__name__', 'serializer')}"
    return list_validator


def decimal(value: Any, /) -> Decimal:
    # We represent decimals using ints or floats when possible and safe.
    # Otherwise, represent as a string to avoid losing precision.

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(value)
    except (ValueError, TypeError):
        raise ValueError(f"Expected a decimal value, got {value!r}")


def enum[T: Enum](enum: type[T], /) -> Validator[T]:
    def enum_validator(value: Any) -> T:
        if isinstance(value, enum):
            return value
        if isinstance(value, str):
            try:
                return enum[value]
            except KeyError:
                msg = (
                    f"Invalid value {value!r}, expected one of {[e.name for e in enum]}"
                )
                raise ValueError(msg)
        msg = f"Expected a string or {enum.__name__} value, got {type(value).__name__}"
        raise ValueError(msg)

    return enum_validator


def text_format(value: Any, /) -> str:
    """
    Normalize text format identifiers by lowercasing and replacing spaces with
    hyphens.

    We recognize common programming languanges, plain text, markdown, etc.
    """
    if not isinstance(value, str):
        raise ValueError(f"Expected a string value, got {type(value).__name__}")
    text = value.lower().replace(" ", "-")
    return TEXT_FORMAT_ALIAS.get(text, text)


def regex(value: Any, /) -> re.Pattern[str]:
    """
    Validate that a value is a valid regular expression pattern.

    Convert it to a Pattern object.
    """
    if isinstance(value, str):
        try:
            return re.compile(value)
        except re.error as e:
            raise ValueError(f"Invalid regular expression pattern: {e}") from e

    msg = f"Expected a string value for regex pattern, got {type(value).__name__}"
    raise ValueError(msg)
