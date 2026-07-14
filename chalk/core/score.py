import operator
from decimal import Decimal
from fractions import Fraction
from typing import Any, Literal, NewType, Protocol, cast, overload

from rich.console import RenderableType
from rich.text import Text

from ..numeric import to_decimal
from ..question import TypeIs

__all__ = [
    "MAX_SCORE",
    "MIN_SCORE",
    "BoundScore",
    "UnboundScore",
    "Score",
    "Numeric",
    "parse_score",
    "validate_score",
    "is_score",
    "is_bound_score",
    "op",
    "div",
    "mul",
    "add",
    "sub",
    "rich_render_percent",
    "rich_render",
]

DecimalScore = NewType("DecimalScore", Decimal)
FractionScore = NewType("FractionScore", Fraction)

BoundScore = DecimalScore | FractionScore
Numeric = Decimal | Fraction | int | float
UnboundScore = Decimal | Fraction
Score = UnboundScore | BoundScore


MAX_SCORE: BoundScore = DecimalScore(Decimal(1))
MIN_SCORE: BoundScore = DecimalScore(Decimal(0))


class BinOp(Protocol):
    @overload
    def __call__(self, x: Fraction, y: Fraction, /) -> Fraction: ...
    @overload
    def __call__(self, x: Decimal, y: Decimal, /) -> Decimal: ...

    def __call__(self, x: Any, y: Any, /) -> Any: ...


@overload
def score(value: Numeric | Score, *, out_of_bound: Literal[True]) -> BoundScore: ...


@overload
def score(value: Numeric | Score, *, out_of_bound: bool = False) -> Score: ...


def score(value: Numeric | Score, *, out_of_bound: bool = False) -> Score:
    """
    Convert the given value to a Score.

    If out_of_bound is True, the value can be outside the [0, 1] range.
    """
    if not out_of_bound and not 0 <= value <= 1:
        raise ValueError(f"Score must be between 0 and 1, got {value}")

    if isinstance(value, (Decimal, Fraction)):
        return cast(BoundScore, value)
    elif isinstance(value, int):
        return cast(BoundScore, Decimal(value))
    elif isinstance(value, float):
        return cast(BoundScore, to_decimal(value))
    else:
        raise TypeError(f"Invalid score type: {type(value)}")


@overload
def parse_score(value: str, *, out_of_bound: Literal[True]) -> BoundScore: ...


@overload
def parse_score(value: str, *, out_of_bound: bool = False) -> Score: ...


def parse_score(value: str, *, out_of_bound: bool = False) -> Score:
    """
    Parse the given string as a score.
    """

    if "/" in value:
        try:
            numerator, denominator = map(int, value.split("/"))
        except ValueError:
            raise ValueError(f"Invalid score format: {value}")
        if not out_of_bound and not 0 <= numerator / denominator <= 1:
            raise ValueError(f"Score must be between 0 and 1, got {value}")
        return FractionScore(Fraction(numerator, denominator))

    return score(to_decimal(value), out_of_bound=out_of_bound)


@overload
def validate_score(value: Any, *, out_of_bound: Literal[True]) -> BoundScore: ...


@overload
def validate_score(value: Any, *, out_of_bound: bool = False) -> Score: ...


def validate_score(value: Any, out_of_bound: bool = False) -> Score:
    """
    Validate the given value as a score.
    """

    if isinstance(value, Numeric):
        return score(value, out_of_bound=out_of_bound)
    elif isinstance(value, str):
        return parse_score(value, out_of_bound=out_of_bound)
    elif isinstance(value, dict) and "numerator" in value and "denominator" in value:
        try:
            numerator = int(value["numerator"])
            denominator = int(value["denominator"])
        except ValueError:
            pass
        else:
            return score(Fraction(numerator, denominator), out_of_bound=out_of_bound)

    raise ValueError(f"Invalid score value: {value!r}")


def is_score(value: Any) -> TypeIs[Score]:
    """
    Check if the given value is a valid score.
    """
    return isinstance(value, (Decimal, Fraction))


def is_bound_score(value: Any) -> TypeIs[BoundScore]:
    """
    Check if the given value is a valid bound score.
    """
    if not is_score(value):
        return False
    return 0 <= value <= 1


#
# Mathematical operations
#
@overload
def div(x: Score, y: Score | int, /, *, check_bounds: Literal[True]) -> BoundScore: ...


@overload
def div(x: Score, y: Score | int, /, *, check_bounds: bool = False) -> Score: ...


def div(x: Score, y: Score | int, /, *, check_bounds: bool = False) -> Score:
    """
    Divide two scores and verify if the result is within bounds.

    Examples:
        >>> div(score(0.5), score(0.25))
        Decimal('2')
    """
    return op(operator.truediv, x, y, check_bounds=check_bounds)


@overload
def mul(x: Score, y: Score | int, /, *, check_bounds: Literal[True]) -> BoundScore: ...


@overload
def mul(x: Score, y: Score | int, /, *, check_bounds: bool = False) -> Score: ...


def mul(x: Score, y: Score | int, /, *, check_bounds: bool = False) -> Score:
    """
    Multiply two scores and verify if the result is within bounds.

    Examples:
        >>> mul(score(0.5), score(0.25))
        Decimal('0.125')
    """

    return op(operator.mul, x, y, check_bounds=check_bounds)


@overload
def add(x: Score, y: Score | int, /, *, check_bounds: Literal[True]) -> BoundScore: ...


@overload
def add(x: Score, y: Score | int, /, *, check_bounds: bool = False) -> Score: ...


def add(x: Score, y: Score | int, /, *, check_bounds: bool = False) -> Score:
    """
    Multiply two scores and verify if the result is within bounds.

    Examples:
        >>> add(score(0.5), score(0.25))
        Decimal('0.75')
    """

    return op(operator.add, x, y, check_bounds=check_bounds)


@overload
def sub(x: Score, y: Score | int, /, *, check_bounds: Literal[True]) -> BoundScore: ...


@overload
def sub(x: Score, y: Score | int, /, *, check_bounds: bool = False) -> Score: ...


def sub(x: Score, y: Score | int, /, *, check_bounds: bool = False) -> Score:
    """
    Multiply two scores and verify if the result is within bounds.

    Examples:
        >>> sub(score(0.5), score(0.25))
        Decimal('0.25')
    """

    return op(operator.sub, x, y, check_bounds=check_bounds)


@overload
def op(op: BinOp, x: Score, y: Score | int, /, *, check_bounds: Literal[True]) -> BoundScore: ...


@overload
def op(op: BinOp, x: Score, y: Score | int, /, *, check_bounds: bool = False) -> Score: ...


def op(op: BinOp, x: Score, y: Score | int, /, *, check_bounds: bool = False) -> Score:
    """
    Perform the given operation on two scores and verify if the result is within bounds.
    """

    if isinstance(x, Decimal):
        if isinstance(y, (Decimal, int)):
            result = op(x, Decimal(y))
        else:
            result = op(x, Decimal(y.numerator) / y.denominator)
    elif isinstance(x, Fraction):
        if isinstance(y, (Fraction, int)):
            result = op(x, Fraction(y))
        else:
            result = op(Decimal(x.numerator) / x.denominator, y)
    else:
        raise TypeError(f"Invalid score type: {type(x)}")

    return score(result, out_of_bound=not check_bounds)


#
# Renderers
#
def render_score(score: Score) -> str:
    if isinstance(score, Decimal):
        return f"{score:.2%}"
    elif isinstance(score, Fraction):
        return f"{score.numerator}/{score.denominator}"
    else:
        raise TypeError(f"Invalid score type: {type(score)}")


def rich_render_percent(score: Score) -> RenderableType:
    color = score_color(score)
    value = round(float(mul(score, 100)), 1)
    return Text(f"{value:.1f}%", style=color)


def rich_render(score: Score) -> RenderableType:
    return Text(render_score(score), style=score_color(score))


def score_color(score: Score) -> str:
    if score <= 0.5:
        return "red"
    elif score <= 0.75:
        return "yellow"
    else:
        return "green"
