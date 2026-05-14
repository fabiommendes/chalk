import sys
from collections import defaultdict
from typing import Any, Callable

import rich

from ..exceptions import ChalkError, Error


def safe[R, **P](func: Callable[P, R]) -> Callable[P, R]:
    """
    A decorator that wraps a function in a try-except block and prints any exceptions that occur.
    """
    import functools
    import traceback

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ChalkError as e:
            e.print()
        except NotImplementedError as e:
            msg = str(e) if e.args else "This feature is not yet implemented"
            rich.print(f"[b red]Not implemented: {msg}[/]", file=sys.stderr)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            traceback.print_exc()

    return wrapper


def validate_options(
    vars: dict[str, Any] | set[str],
    valid_options: set[str],
    /,
    msg: str = "Invalid option: {option}",
) -> None:
    """
    Validate that the given options are in the set of valid options.
    """
    keys = vars.keys() if isinstance(vars, dict) else vars
    for option in keys - valid_options:
        raise Error.INVALID_FIELD(msg.format(option=option))


def to_dict_of_lists[K, V](d: list[dict[K, V]]) -> dict[K, list[V]]:
    """
    Map a list of dictionaries to a dictionary of lists.
    """
    result: dict[K, list[V]] = defaultdict(list)
    for item in d:
        for key, value in item.items():
            result[key].append(value)
    return result


def from_dict_of_lists[K, V](d: dict[K, list[V]]) -> list[dict[K, V]]:
    """
    Map a dictionary of lists to a list of dictionaries.
    """
    keys = d.keys()
    values = zip(*d.values())
    return [dict(zip(keys, v)) for v in values]
