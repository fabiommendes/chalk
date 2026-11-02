import builtins
import re
from collections.abc import Callable
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from functools import singledispatch
from typing import Any, Literal

from ..core import disqualification as _disqualification
from ..core.decimal import render_decimal
from ..core.score import BoundScore
from .protocols import JSONSerializable, Serializable

type Serializer[T] = Callable[[T], Any]

HUNDRED_DIVISORS = {2: 50, 4: 25, 5: 20, 10: 10, 20: 5, 25: 4, 50: 2}


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


def one_of(
    mapping: dict[type, Serializer[Any]],
    /,
    on_error: Literal["raise", "ignore"] = "raise",
    nullable: bool = False,
) -> Serializer[Any]:
    """
    A helper function to create a serializer for a value that can be one of several types.

    Args:
        mapping:
            A dictionary mapping types to their corresponding serializer functions.
        on_error:
            Determines the behavior when a value's type is not in the mapping.
            - "raise": Raises a TypeError if the value's type is not in the mapping
            - "ignore": Returns the value as-is if the type is unknown.
            Usually you want to use "ignore" when declaring BeforeSerializers so
            pydantic can handle the type checking


    """

    expected_types = ", ".join(typ.__name__ for typ in mapping.keys())

    @singledispatch
    def one_of_serializer(value: Any) -> Any:
        if on_error == "raise":
            raise TypeError(f"Value {value} is not one of the expected types: {expected_types}")
        return value

    for typ, fn in mapping.items():
        one_of_serializer.register(typ, fn)

    if nullable:
        one_of_serializer.register(type(None), lambda _: None)

    return one_of_serializer


def optional_list[T](fn: Serializer[T], /) -> Serializer[builtins.list[T] | None]:
    """
    A helper function to create a serializer for an optional list of items.
    """

    def optional_list_serializer(values: builtins.list[T] | None) -> Any:
        if values is None:
            return None
        return [fn(value) for value in values]

    optional_list_serializer.__name__ = f"optional_list_{getattr(fn, '__name__', 'serializer')}"
    return optional_list_serializer


def decimal(value: Decimal, /) -> float | int | str:
    # We represent decimals using ints or floats when possible and safe.
    # Otherwise, represent as a string to avoid losing precision.
    as_string = str(value)
    if "." not in as_string:
        return int(as_string)

    # Use float if it truncates up to 2 decimal places.
    as_float = round(float(as_string), 2)
    if str(as_float) == as_string:
        return as_float
    return as_string


def enum(value: Enum, /) -> str:
    return value.name


def regex(value: re.Pattern[str], /) -> str:
    return value.pattern


def score(value: BoundScore, /) -> str:
    """
    Serialize a Score object to a string.

    Strings are the safest way to store numbers when precision is important.

    Examples:
        >>> score(Decimal(0.75))
        '0.75'
        >>> score(Fraction(3, 4))
        '0.75'
        >>> score(Fraction(1, 3))
        '1/3'
    """
    if isinstance(value, Decimal):
        return render_decimal(value)
    elif isinstance(value, Fraction):
        if value.denominator in HUNDRED_DIVISORS:
            multiplier = HUNDRED_DIVISORS[value.denominator]
            pc_digits = [*str(value.numerator * multiplier)]
            match pc_digits:
                case []:
                    raise ValueError(f"Invalid score: {value}")
                case [d]:
                    return f"0.0{d}"
                case [d1, d2]:
                    return f"0.{d1}{d2}"
                case [*head, d1, d2]:
                    return f"{''.join(head)}.{d1}{d2}"
        return f"{value.numerator}/{value.denominator}"
    return decimal(value)


def disqualification(value: _disqualification.Disqualification, /) -> str:
    """
    Serialize a Score or Disqualification object to a string.
    """
    return str(value)


#
# Chalk protocols
#
def serializable(value: Serializable, /) -> str:
    return value.serialize()


def json_serializable(value: JSONSerializable, /) -> str:
    return value.to_json()
