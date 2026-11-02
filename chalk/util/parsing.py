import re
from collections.abc import Callable
from decimal import Decimal
from typing import Any, NamedTuple, overload

PARENS = re.compile(r"(?P<parens>[()])|(?P<other>[^()]+)")
NUMBER = re.compile(r"(\s*([+-]?\d+(?:\.\d*)?|\.\d+))")


class Parsed[T](NamedTuple):
    remaining: str
    value: T


type Parser[T] = Callable[[str], Parsed[T]]


def attempt[T](parser: Parser[T], src: str, /) -> Parsed[T | None]:
    """
    Attempt to parse the given string with the given parser.

    If the parser succeeds, return the parsed value. If the parser raises a
    ValueError, return None.
    """
    try:
        return parser(src)  # type: ignore
    except ValueError:
        return Parsed(src, None)


@overload
def seq[T](parser_a: Parser[T], src: str, /) -> Parsed[tuple[T]]: ...


@overload
def seq[T1, T2](
    p1: Parser[T1], p2: Parser[T2], src: str, /
) -> Parsed[tuple[T1, T2]]: ...


@overload
def seq[T1, T2, T3](
    p1: Parser[T1], p2: Parser[T2], p3: Parser[T3], src: str, /
) -> Parsed[tuple[T1, T2, T3]]: ...


@overload
def seq[T1, T2, T3, T4](
    p1: Parser[T1], p2: Parser[T2], p3: Parser[T3], p4: Parser[T4], src: str, /
) -> Parsed[tuple[T1, T2, T3, T4]]: ...


def seq(*args: Any) -> Parsed[tuple[Any, ...]]:
    """
    Combine two parsers sequentially.

    The resulting parser will first apply parser a to the input string, then
    apply parser b to the remaining string after a. If both parsers succeed,
    the result will be a tuple of the values returned by a and b.
    """
    values = []
    *parsers, src = args
    for parser in parsers:
        src, value = parser(src)
        values.append(value)
    return Parsed(src, tuple(values))


def read_spaces(src: str) -> Parsed[None]:
    """
    Read leading whitespace from the given string.

    Return the remaining string and None.
    """
    return Parsed(src.lstrip(), None)


def read_number(src: str) -> Parsed[Decimal]:
    """
    Read a number from the beginning of the given string.

    Return the remaining string and the parsed number as a Decimal or raise
    ValueError if the string does not start with a valid number.
    """
    if (m := NUMBER.match(src)) is None:
        raise ValueError(f"Expected a number at the beginning of {src!r}")
    return Parsed(src[m.end() :], Decimal(m.group(1)))


def read_parens(src: str) -> Parsed[str]:
    """
    Read a parenthesized string from the given source string.

    Return the remaining string and the content of the parentheses or raise
    ValueError if the string does not start with a parenthesized content.
    """
    src = src.lstrip()
    if not src.startswith("("):
        raise ValueError(f"Expected a parenthesized string, got {src!r}")
    src.removeprefix("(")
    depth = 1
    parts: list[str] = []
    for part in PARENS.finditer(src):
        if part.group("parens") == "(":
            depth += 1
        elif part.group("parens") == ")":
            depth -= 1
            if depth == 0:
                remaining = src[part.end() :]
                value = "".join(parts).strip()
                return Parsed(remaining, value)
        parts.append(part.group(0))

    raise ValueError(f"Unmatched parentheses in {src!r}")
