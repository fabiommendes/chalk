#
# Simple conversion functions
#
from decimal import Decimal, InvalidOperation
from fractions import Fraction

Numeric = int | float | Decimal | Fraction

__all__ = [
    "Numeric",
    "to_decimal",
    "add",
    "sub",
    "mul",
    "div",
]


def to_decimal(value: Numeric | str, /) -> Decimal:
    """
    Convert the given numeric value to a Decimal.
    """
    try:
        if type(value) is Decimal:
            return value
        elif isinstance(value, int | float):
            return Decimal(value)
        elif isinstance(value, Fraction):
            return Decimal(value.numerator) / value.denominator
        return Decimal(value)
    except InvalidOperation as e:
        raise ValueError(f"Invalid numeric value: {value}") from e


#
# Basic operations
#
def add(x: Numeric, y: Numeric, /) -> Numeric:
    """
    Add two numeric values.
    """
    x, y = _no_floats(x, y)
    if isinstance(x, (Fraction, int)) and isinstance(y, (Fraction, int)):
        return x + y
    return to_decimal(x) + to_decimal(y)


def sub(x: Numeric, y: Numeric, /) -> Numeric:
    """
    Subtract two numeric values.
    """
    x, y = _no_floats(x, y)
    if isinstance(x, (Fraction, int)) and isinstance(y, (Fraction, int)):
        return x - y
    return to_decimal(x) - to_decimal(y)


def mul(x: Numeric, y: Numeric, /) -> Numeric:
    """
    Multiply two numeric values.
    """
    x, y = _no_floats(x, y)
    if isinstance(x, (Fraction, int)) and isinstance(y, (Fraction, int)):
        return x * y
    return to_decimal(x) * to_decimal(y)


def div(x: Numeric, y: Numeric, /) -> Numeric:
    """
    Divide two numeric values.
    """
    x, y = _no_floats(x, y)
    if isinstance(x, (Fraction, int)) and isinstance(y, (Fraction, int)):
        return x / y
    return to_decimal(x) / to_decimal(y)


#
# Utilities
#
_NumericNoFloat = int | Decimal | Fraction


def _no_float(value: Numeric, /) -> _NumericNoFloat:
    """
    Convert the given numeric value to a type that does not include float.
    """
    if isinstance(value, float):
        return Decimal(value)
    return value


def _no_floats(x: Numeric, y: Numeric, /) -> tuple[_NumericNoFloat, _NumericNoFloat]:
    """
    Convert the given numeric values to types that do not include float.
    """
    return _no_float(x), _no_float(y)
