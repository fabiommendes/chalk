from __future__ import annotations

import decimal
from contextlib import contextmanager
from decimal import Decimal
from logging import getLogger
from typing import TYPE_CHECKING, Callable, Generator

if TYPE_CHECKING:
    pass

log = getLogger(__name__)

#: Control global decimal precision
DECIMAL_PRECISION = 2


def set_decimal_precision(precision: int) -> None:
    """
    Set the global decimal precision for grade rendering.

    Usually called once when the global configuration is loaded.
    """
    if precision < 0:
        raise ValueError("Precision must be a non-negative integer.")

    global DECIMAL_PRECISION
    DECIMAL_PRECISION = precision


@contextmanager
def default_decimal_precision() -> Generator[Callable[[Decimal], Decimal], None, None]:
    """
    Get the current global decimal precision for grade rendering.
    """
    old_round = decimal.getcontext().rounding
    decimal.getcontext().rounding = decimal.ROUND_HALF_UP
    try:
        yield as_chalk_decimal
    finally:
        decimal.getcontext().rounding = old_round


def get_decimal_precision() -> int:
    """
    Get the current global decimal precision for grade rendering.
    """
    return DECIMAL_PRECISION


def get_decimal_context(_memo: dict[int, decimal.Context] = {}) -> decimal.Context:
    """
    Get a decimal context with the current global precision for grade rendering.
    """
    try:
        return _memo[id(DECIMAL_PRECISION)]
    except KeyError:
        context = decimal.Context(
            rounding=decimal.ROUND_HALF_UP,
        )
        _memo[id(DECIMAL_PRECISION)] = context
        return context


def as_chalk_decimal(value: Decimal | float | int | str, /) -> Decimal:
    """
    Normalize a Decimal value to the current global precision for grade rendering.
    """
    if isinstance(value, (float, int)):
        value = Decimal(value)
    elif isinstance(value, Decimal):
        pass
    elif isinstance(value, str):
        value = Decimal(value)

    return chalk_decimal(value)


def chalk_decimal(value: Decimal) -> Decimal:
    """
    Normalize a Decimal value to the current global precision for grade rendering.
    """
    value = value.normalize()
    _, _, exponent = value.as_tuple()

    if not isinstance(exponent, int):
        pass
    elif exponent < 0:
        try:
            value = round(value, DECIMAL_PRECISION)
        except decimal.DecimalException:
            log.info(f"Failed to round value {value} to precision {DECIMAL_PRECISION}.")

    return value


def render_decimal(value: Decimal | float | int, /) -> str:
    """
    Format a Decimal value as a string with the current global precision.
    """
    if not isinstance(value, Decimal):
        value = Decimal(value)

    with default_decimal_precision() as normalize:
        value = normalize(value)
        return "{value:.{precision}f}".format(value=value, precision=get_decimal_precision())
