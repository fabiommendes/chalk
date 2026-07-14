import builtins
import re
from decimal import Decimal
from enum import Enum
from typing import Any, Callable

from ..core import disqualification as _disqualification
from ..core.decimal import as_chalk_decimal
from ..core.score import BoundScore, Numeric, parse_score
from ..core.score import score as read_score
from .protocols import HasId, JSONSerializable, Serializable

type Validator[T] = Callable[[Any], T]

__all__ = [
    "Validator",
    "typecheck",
    "optional",
    "one_of",
    "any",
    "list",
    "unique_by",
    "optional_list",
    "clean_dict",
    "decimal",
    "enum",
    "text_format",
    "regex",
    "serializable",
    "json_serializable",
    "id",
]

TEXT_FORMAT_ALIAS = {
    "plain": "text",
    "plain-text": "text",
    "md": "markdown",
    "py": "python",
    "js": "javascript",
    "c++": "cpp",
    "c#": "csharp",
}


def typecheck[T](typ: type[T]) -> Validator[T]:
    """
    A helper function to create a validator for a specific type.
    """

    def type_validator(value: Any) -> T:
        if not isinstance(value, typ):
            raise ValueError(f"Expected {typ.__name__}, got {type(value).__name__}")
        return value

    type_validator.__name__ = f"type_{typ.__name__}"
    return type_validator


def optional[T](fn: Validator[T], /) -> Validator[T | None]:
    """
    A helper function to create a validator for an optional field.
    """

    def optional_validator(value: T | None) -> Any:
        if value is None:
            return None
        return fn(value)

    optional_validator.__name__ = f"optional_{_fname(fn)}"
    return optional_validator


def one_of[T1, T2](fn1: Validator[T1], fn2: Validator[T2], /) -> Validator[T1 | T2]:
    """
    A helper function to create a validator that accepts one of two validators.
    """

    def one_of_validator(value: Any) -> Any:
        try:
            return fn1(value)
        except ValueError:
            pass
        try:
            return fn2(value)
        except ValueError:
            pass
        raise ValueError(
            f"Expected one of {fn1.__name__} or {fn2.__name__}, got {type(value).__name__}"
        )

    one_of_validator.__name__ = f"one_of_{_fname(fn1)}_{_fname(fn2)}"
    return one_of_validator


def any() -> Validator[Any]:
    """
    A helper function to create a validator that accepts any value.
    """

    def any_validator(value: Any) -> Any:
        return value

    any_validator.__name__ = "any"
    return any_validator


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

    list_validator.__name__ = f"list_{_fname(fn)}"
    return list_validator


def disqualification(value: Any, /) -> _disqualification.Disqualification:
    """
    Validate that a value is a valid disqualification.

    A disqualification must be a string.
    """
    if isinstance(value, str):
        return _disqualification.parse(value)
    elif isinstance(value, _disqualification.Disqualification):
        return value
    raise ValueError(f"Expected a string value for disqualification, got {_clsname(value)}")


def unique_by[T](
    key: Callable[[T], Any],
    /,
    *,
    type: type[T],
    nullable: bool = False,
) -> Validator[Any]:
    """
    A helper function to create a validator for a sequence of items that ensures
    that the items are unique by a given key function.

    It is usually better used as an AfterValidator since it does not transform
    the values, but rather checks for uniqueness.
    """

    def unique_by_validator(values: Any) -> Any:
        seen = set()
        if nullable and values is None:
            return []

        for i, value in enumerate(values):
            k = key(value)
            if k in seen:
                raise ValueError(f"Duplicate value at index {i}: {k!r}")
            seen.add(k)
            if not isinstance(value, type):
                msg = f"Expected {_clsname(type)} at index {i}, got {_clsname(value)}"
                raise ValueError(msg)

        return values

    unique_by_validator.__name__ = f"unique_by_{_fname(key)}"
    return unique_by_validator


def optional_list[T](fn: Validator[T], /) -> Validator[builtins.list[T] | None]:
    """
    A list of T's. If the list is empty, it is represented as None.
    """

    def optional_list_validator(values: builtins.list[T] | None) -> Any:
        if values is None:
            return None
        if isinstance(values, (str, bytes)):
            raise ValueError(f"Expected an iterable, got {type(values).__name__}")

        try:
            values_iter = iter(values)
        except TypeError:
            raise ValueError("Expected an iterable")

        data = [fn(value) for value in values_iter]
        return None if not data else data

    optional_list_validator.__name__ = f"optional_list_{_fname(fn)}"
    return optional_list_validator


def clean_dict[T](fn: Validator[T], /) -> Validator[dict[str, T]]:
    """
    A helper function to create a validator for a dictionary with string keys
    that remove None values.
    """

    def dict_validator(values: dict[str, T]) -> Any:
        if not isinstance(values, dict):
            raise ValueError(f"Expected a dictionary, got {type(values).__name__}")
        return {str(key): fn(value) for key, value in values.items() if value is not None}

    dict_validator.__name__ = f"clean_dict_{_fname(fn)}"
    return dict_validator


def decimal(value: Any, /) -> Decimal:
    # We represent decimals using ints or floats when possible and safe.
    # Otherwise, represent as a string to avoid losing precision.

    if isinstance(value, Decimal):
        return as_chalk_decimal(value)

    try:
        return as_chalk_decimal(value)
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
                msg = f"Invalid value {value!r}, expected one of {[e.name for e in enum]}"
                raise ValueError(msg)
        msg = f"Expected a string or {enum.__name__} value, got {_clsname(value)}"
        raise ValueError(msg)

    return enum_validator


def text_format(value: Any, /) -> str:
    """
    Identify valid values for a Textual question text_format field.

    This function normalizes identifiers by lowercasing and replacing spaces with
    hyphens.

    We recognize common programming languanges, plain text, markdown, etc.
    """
    if not isinstance(value, str):
        raise ValueError(f"Expected a string value, got {_clsname(value)}")
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

    msg = f"Expected a string value for regex pattern, got {_clsname(value)}"
    raise ValueError(msg)


def out_of_bounds_score(value: Any, /) -> BoundScore:
    """
    Validate that a value is a valid score, allowing for out-of-bounds values.

    A score must be a decimal number, but can be outside the [0, 1] range.
    """
    return score(value, out_of_bound=True)


def score(value: Any, *, out_of_bound: bool = False) -> BoundScore:
    """
    Validate that a value is a valid score.

    A score must be a decimal number between 0 and 1 (inclusive).
    """
    if isinstance(value, str):
        return parse_score(value, out_of_bound=out_of_bound)
    if isinstance(value, Numeric):
        return read_score(value, out_of_bound=out_of_bound)

    raise ValueError(f"Expected a numeric or string value for score, got {_clsname(value)}")


#
# Custom chalk protocols
#
def serializable[T: Serializable](typ: type[T], /) -> Validator[T]:
    """
    Return a validator for a type that implements the Serializable protocol.
    """

    def serializable_validator(value: Any) -> T:
        if isinstance(value, typ):
            return value
        if isinstance(value, str):
            try:
                return typ.deserialize(value)
            except ValueError:
                raise
            except Exception as e:
                msg = f"the deserialize method raised an unexpected exception: {_clsname(e)}"
                raise RuntimeError(msg) from e

        msg = f"Expected a string or {typ.__name__} value, got {_clsname(value)}"
        raise ValueError(msg)

    return serializable_validator


def json_serializable[T: JSONSerializable](typ: type[T], /) -> Validator[T]:
    """
    Return a validator for a type that implements the JSONSerializable protocol.
    """

    def json_serializable_validator(value: Any) -> T:
        if isinstance(value, typ):
            return value
        if isinstance(value, str):
            try:
                return typ.from_json(value)
            except ValueError:
                raise
            except Exception as e:
                msg = f"the from_json method raised an unexpected exception: {_clsname(e)}"
                raise RuntimeError(msg) from e

        msg = f"Expected a string or {typ.__name__} value, got {_clsname(value)}"
        raise ValueError(msg)

    return json_serializable_validator


#
# Utilities
#
def _fname(fn: Callable[..., Any], /) -> str:
    return getattr(fn, "__name__", "fn")


def _clsname(obj: Any, /) -> str:
    if isinstance(obj, type):
        return getattr(obj, "__name__", "type")
    return getattr(type(obj), "__name__", "obj")


def id[T = str](obj: HasId[T], /) -> T:
    """
    A helper function to extract the id from an object that implements the HasId protocol.
    """
    return obj.id
