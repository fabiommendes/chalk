from __future__ import annotations

import decimal
from contextlib import contextmanager
from decimal import Decimal
from functools import total_ordering
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generator,
    Literal,
    overload,
)

from ..types import JSON
from ..util.parsing import read_parens
from . import adjustment as adj
from . import disqualification as dq
from .adjustment import Adjustment
from .disqualification import Disqualification

if TYPE_CHECKING:
    pass

DECIMAL_PRECISION = 2

type Context = Literal["assignment", "question", "final"]


__all__ = [
    "Grade",
    "set_precision",
    "get_precision",
    "default_precision",
]


@total_ordering
class Grade:
    """
    Represent a grade with some optional context information.

    The context can include grade overrides, penalties, or disqualifications.
    The baseline grade value is what is considered the final grade for the
    given assignment.

    A *disqualified* grade is usually not even considered for grading and is
    assigned a default value (usually 0) without even considering the actual
    grade value.

    An *adjusted* grade is usually graded as usual, but then some later
    adjustments are applied to the grade value due to consideration such as
    bonus points or penalties, cancelling the question or any other reason.
    """

    _adjustment: Adjustment | None
    _disqualification: Disqualification | None

    #: Defined if this grade overrides another previous grade
    @property
    def adjustment(self) -> Adjustment | None:
        return self._adjustment

    #: Defined if this grade is disqualified for some reason. Prints this value
    #: instead of the grade value when rendered. Usually disqualified grades
    #: have a value of 0, but the user is able to set other values like negative
    #: or some specified threshold.
    @property
    def disqualification(self) -> Disqualification | None:
        return self._disqualification

    #: True if this grade has no overrides or disqualifications, and is a simple grade.
    @property
    def is_plain(self) -> bool:
        return self._adjustment is None and self._disqualification is None

    @property
    def value(self) -> Decimal:
        """
        The real decimal value of the grade, after applying any adjustments.
        """
        if self._adjustment is None:
            return self._value
        return self._adjustment.apply(self._value)

    @property
    def non_adjusted(self) -> Decimal:
        """
        The original decimal value of the grade, without applying any adjustments.
        """
        return self._value

    @classmethod
    def parse(cls, src: str, /) -> Grade:
        """
        Parse a string representation of a grade into a Grade object.
        """
        return parse(src)

    def __init__(
        self,
        value: str | float | int | Decimal = "0",
        *,
        adjustment: Adjustment | None = None,
        disqualification: Disqualification | None = None,
    ):
        if adjustment and disqualification:
            msg = "A grade cannot have both an override and a disqualification."
            raise ValueError(msg)

        value = normalize(Decimal(value, context=get_context()))
        self._value = value
        self._adjustment = adjustment
        self._disqualification = disqualification

    def __str__(self) -> str:
        return self.to_json(force_string=True)

    def __repr__(self) -> str:
        kwargs = []
        if self._adjustment is not None:
            kwargs.append(f"adjustment={self._adjustment!r}")
        if self._disqualification is not None:
            kwargs.append(f"disqualification={self._disqualification!r}")
        if kwargs:
            return f"Grade({self._value}, {', '.join(kwargs)})"
        return f"Grade({self._value})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Grade):
            return (
                self._value == other._value
                and self._adjustment == other._adjustment
                and self._disqualification == other._disqualification
            )
        return self._value.__eq__(other)

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Grade):
            return self.value < other.value
        return self._value.__lt__(other)  # type: ignore

    @overload
    def to_json(self, *, force_string: Literal[True]) -> str: ...

    @overload
    def to_json(self, *, force_string: bool = False) -> JSON: ...

    def to_json(self, *, force_string: bool = False) -> JSON:
        """
        Convert the grade to a JSON-serializable representation.

        For simple grades, it is either a float, when it is safe to represent
        the grade as a number, or a string with extra context information.
        """
        # Display disqualified grades
        if (disqualification := self._disqualification) is not None:
            prefix = disqualification.display()
            if self._value == 0 and self._adjustment is None:
                return prefix
            else:
                return f"{prefix} ({self.disqualify(None)})"

        # Display adjusted grades
        if (adjustment := self._adjustment) is not None:
            return adjustment.represent(self._value)

        v = self._value
        if force_string:
            return format_decimal(v)

        if v.adjusted() >= 0:
            return int(v)
        elif (f := float(v)) == v:
            return f
        else:
            return str(v)

    @classmethod
    def from_json(cls, data: JSON, /) -> Grade:
        """
        Convert a JSON-serializable representation back to a Grade object.

        For simple grades, it is either a float or a string.
        """
        if isinstance(data, Grade):
            return data
        if isinstance(data, (int, float)):
            return Grade(data)
        elif isinstance(data, str):
            return parse(data)
        else:
            raise ValueError(f"Cannot convert {data!r} to a Grade.")

    def disqualify(self, disqualification: Disqualification | None, /) -> Grade:
        """
        Disqualify this grade with the given disqualification reason.
        """
        return Grade(
            self._value,
            disqualification=disqualification,
            adjustment=self._adjustment,
        )

    def adjust(self, adjustment: Adjustment | None, /) -> Grade:
        """
        Adjust this grade with the given adjustment.
        """
        return Grade(
            self._value,
            adjustment=adjustment,
            disqualification=self._disqualification,
        )


def parse(src: str) -> Grade:
    """
    Parse a string representation of a grade into a Grade object.
    """

    rest = src.strip()
    # First we try the simple case where the string is just a number.
    try:
        return Grade(Decimal(rest))
    except (ValueError, decimal.DecimalException):
        pass

    # Now we try to read disqualified grades.
    try:
        [rest, reason] = dq.read(rest)
        rest = rest.strip()
        if not rest:
            return Grade(0, disqualification=reason)

        rest, data = read_parens(rest)
        if rest.strip():
            msg = f"Unexpected trailing characters after disqualification: {rest!r}"
            raise ValueError(msg)

        return parse(data).disqualify(reason)
    except ValueError:
        pass

    # Finally, we try to read adjusted grades.
    adjustment, value = adj.parse(rest)
    return Grade(value, adjustment=adjustment)


def validate_grade(value: Any) -> Grade:
    """
    Convert a value to a Grade object.

    If the value is already a Grade, it is returned as-is. Raise a ValueError
    if the value cannot be converted to a Grade.
    """
    if isinstance(value, Grade):
        return value
    elif isinstance(value, str):
        return parse(value)
    elif isinstance(value, (int, float, Decimal)):
        return Grade(value)
    else:
        raise ValueError(f"Cannot convert {value!r} to a Grade.")


def format_decimal(value: Decimal) -> str:
    """
    Format a Decimal value as a string with the current global precision.
    """
    with default_precision() as normalize:
        value = normalize(value)
        return "{value:.{precision}f}".format(value=value, precision=get_precision())


#
# Control global decimal precision
#
def set_precision(precision: int) -> None:
    """
    Set the global decimal precision for grade rendering.

    Usually called once when the global configuration is loaded.
    """
    if precision < 0:
        raise ValueError("Precision must be a non-negative integer.")

    global DECIMAL_PRECISION
    DECIMAL_PRECISION = precision


@contextmanager
def default_precision() -> Generator[Callable[[Decimal], Decimal], None, None]:
    """
    Get the current global decimal precision for grade rendering.
    """
    old_round = decimal.getcontext().rounding
    decimal.getcontext().rounding = decimal.ROUND_HALF_UP
    try:
        yield normalize
    finally:
        decimal.getcontext().rounding = old_round


def get_precision() -> int:
    """
    Get the current global decimal precision for grade rendering.
    """
    return DECIMAL_PRECISION


def get_context(_memo: dict[int, decimal.Context] = {}) -> decimal.Context:
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


def normalize(value: Decimal) -> Decimal:
    """
    Normalize a Decimal value to the current global precision for grade rendering.
    """
    value = value.normalize()

    if value.adjusted() >= 0:
        return value
    try:
        return round(value, DECIMAL_PRECISION)
    except decimal.DecimalException:
        print("round error", value, value.as_tuple())
        return value
