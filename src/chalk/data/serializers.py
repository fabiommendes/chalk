import builtins
from decimal import Decimal
from enum import Enum
from typing import Any, Callable

type Serializer[T] = Callable[[T], Any]


def optional[T](fn: Serializer[T], /) -> Serializer[T | None]:
    """
    A helper function to create a serializer for an optional field.
    """

    def optional_serializer(value: T | None) -> Any:
        if value is None:
            return None
        return fn(value)

    optional_serializer.__name__ = f"optional_{getattr(fn, '__name__', 'serializer')}"
    return optional_serializer


def list[T](fn: Serializer[T], /) -> Serializer[builtins.list[T]]:
    """
    A helper function to create a serializer for a list of items.
    """

    def list_serializer(values: builtins.list[T]) -> Any:
        return [fn(value) for value in values]

    list_serializer.__name__ = f"list_{getattr(fn, '__name__', 'serializer')}"
    return list_serializer


def decimal(value: Decimal, /) -> Any:
    # We represent decimals using ints or floats when possible and safe.
    # Otherwise, represent as a string to avoid losing precision.

    as_string = str(value)
    if "." not in as_string:
        return int(as_string)

    # Use float if it truncates up to 2 decimal places.
    if (as_float := round(float(as_string), 2)) == float(as_string):
        return as_float

    return as_string


def enum(value: Enum, /) -> str:
    return value.name
