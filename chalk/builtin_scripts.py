"""
Module with builtin transformators and validators for chalk responses.
"""

from typing import Any, Callable, overload

from unidecode import unidecode

from .core import AnyAnswer

type Transform = Callable[[AnyAnswer | None], AnyAnswer | None]
type Validator = Callable[[AnyAnswer | None], bool]

TRANSFORM_REGISTRY: dict[str, Transform] = {}
VALIDATOR_REGISTRY: dict[str, Validator] = {}


@overload
def transform(
    name: str, *, doc: str | None = None
) -> Callable[[Transform], Transform]: ...


@overload
def transform(name: str, func: Transform, *, doc: str | None = None) -> Transform: ...


def transform(
    name: str, func: Transform | None = None, *, doc: str | None = None
) -> Any:
    """
    A decorator that marks a function as a response transformation.
    """
    if func is None:
        return lambda f: transform(name, f, doc=doc)

    func._is_transform = True  # type: ignore[attr-defined]
    if doc is not None:
        func.__doc__ = doc
    TRANSFORM_REGISTRY[name or func.__name__] = func
    return func


@overload
def validator(
    name: str, *, doc: str | None = None
) -> Callable[[Validator], Validator]: ...


@overload
def validator(name: str, func: Validator, *, doc: str | None = None) -> Validator: ...


def validator(
    name: str, func: Validator | None = None, *, doc: str | None = None
) -> Any:
    """
    A decorator that marks a function as a response validator.
    """
    if func is None:
        return lambda f: validator(name, f, doc=doc)

    func._is_validator = True  # type: ignore[attr-defined]
    if doc is not None:
        func.__doc__ = doc
    VALIDATOR_REGISTRY[name or func.__name__] = func
    return func


def string_transform(
    name: str, func: Callable[[str], AnyAnswer | None], *, doc: str | None = None
) -> Transform:
    """
    A decorator that marks a function as a response transformation that operates on strings.
    """

    def wrapper(answer: AnyAnswer | None, /) -> AnyAnswer | None:
        if isinstance(answer, str):
            return func(answer)
        return answer

    return transform(name, wrapper, doc=doc)


def string_validator(
    name: str, func: Callable[[str], bool], *, doc: str | None = None
) -> Validator:
    """
    A decorator that marks a function as a response validator that operates on strings.
    """

    def wrapper(answer: AnyAnswer | None, /) -> bool:
        if isinstance(answer, str):
            return func(answer)
        return False

    return validator(name, wrapper, doc=doc)


# ==============================================================================
# Transforms
# ==============================================================================#
string_transform(
    "text.nonempty",
    lambda s: not s.strip() and None or s,
    doc="Normalize empty textual answers as not-responded",
)
string_transform(
    "text.strip",
    str.strip,
    doc="Remove leading and trailing whitespace",
)
string_transform(
    "text.lower",
    str.lower,
    doc="Convert textual answers to lowercase",
)
string_transform(
    "text.upper",
    str.upper,
    doc="Convert textual answers to uppercase",
)
string_transform(
    "text.unidecode",
    unidecode,
    doc="Remove accents and other diacritics",
)

# ==============================================================================#
# Validators
# ==============================================================================
string_validator(
    "text.nonempty",
    lambda s: bool(s.strip()),
    doc="Check if answer is non-empty",
)
string_validator(
    "text.digits",
    lambda s: s.isdigit(),
    doc="Check if answer contains only digits",
)
string_validator(
    "text.alpha",
    lambda s: s.isalpha(),
    doc="Check if answer contains only letters",
)
string_validator(
    "text.alphanumeric",
    lambda s: s.isalnum(),
    doc="Check if answer contains only letters and digits",
)
