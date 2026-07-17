from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any, Callable, Literal, cast

import rich
from rich.prompt import Prompt

if TYPE_CHECKING:
    pass


def safe[R, **P](func: Callable[P, R]) -> Callable[P, R]:
    """
    A decorator that wraps a function in a try-except block and prints any exceptions that occur.
    """
    import functools
    import traceback

    from ..core import ChalkErrorEnum

    @functools.wraps(func)
    def wrapper(*args, **kwargs):  # type: ignore
        try:
            return func(*args, **kwargs)
        except ChalkErrorEnum as e:
            e.print()
        except Exception as e:
            rich.print(f"[b red]Error:[/] {e}", file=sys.stderr)
            if is_debug_mode():
                traceback.print_exc()

    return cast(Callable[P, R], wrapper)


def is_debug_mode() -> bool:
    """
    Returns True if the CHALK_DEBUG environment variable is set to "1", False otherwise.
    """

    thruthy = ("1", "true")
    return (
        os.environ.get("CHALK_DEBUG", "0").lower() in thruthy
        or os.environ.get("DEBUG", "0").lower() in thruthy  
    )  # fmt: skip


def validate_options(
    vars: dict[str, Any] | set[str],
    valid_options: set[str],
    /,
    msg: str = "Invalid option: {option}",
) -> None:
    """
    Validate that the given options are in the set of valid options.
    """
    from ..core import ChalkError

    keys = vars.keys() if isinstance(vars, dict) else vars
    for option in keys - valid_options:
        raise ChalkError.INVALID_FIELD(msg.format(option=option))


def __getattr__(name: str) -> Any:
    models = ("Quiz", "Question", "Response", "SystemError")
    if name in models:
        from .. import core

        return getattr(core, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def yn_prompt(message: str, default: Literal["y", "n", "N"] = "y") -> bool | None:
    match Prompt.ask(message, choices=["y", "n", "N"], default=default):
        case "y":
            return True
        case "n":
            return False
        case "N":
            return None
        case _:
            raise RuntimeError("Invalid choice")
