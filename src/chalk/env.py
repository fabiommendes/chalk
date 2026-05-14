import os
from pathlib import Path
from typing import overload

from rich.prompt import Prompt


def get_env_classroom(value: str | None, interactive: bool | None = None) -> str:
    """
    Use either the given value or compute the default classroom name from the environment.
    """
    if value is not None:
        return value

    if get_interactivity(interactive):
        return Prompt.ask("Classroom name", default=get_env_classroom(None))

    cwd = Path.cwd()
    return cwd.name


def get_env_teacher(value: str | None, interactive: bool | None = None) -> str:
    """
    Use either the given value or compute the default teacher name from the environment.
    """
    if value is not None:
        return value

    if get_interactivity(interactive):
        return Prompt.ask("Teacher name", default=get_env_teacher(None))

    if value := os.environ.get("CHALK_USER"):
        return value

    return os.getlogin()


def get_interactivity(value: bool | None) -> bool:
    """
    Determine whether to use interactive prompts based on the given value and the environment.
    """
    if value is not None:
        return value

    return (
        os.isatty(0)
        and os.isatty(1)
        and os.environ.get("CHALK_INTERACTIVE", "0") != "0"
    )


@overload
def ask_optional_string(
    prompt: str,
    value: str | None = None,
    *,
    default: str,
    interactive: bool | None = None,
) -> str: ...


@overload
def ask_optional_string(
    prompt: str,
    value: str | None = None,
    *,
    default: None = None,
    interactive: bool | None = None,
) -> str | None: ...


def ask_optional_string(
    prompt: str,
    value: str | None = None,
    *,
    default: str | None = None,
    interactive: bool | None = None,
) -> str | None:
    """
    Ask the user for a value using a prompt, with an optional default value.
    """
    if value is not None:
        return value
    elif get_interactivity(interactive) and default is not None:
        out = Prompt.ask(prompt, default=default)
        return out if out else default
    elif get_interactivity(interactive):
        out = Prompt.ask(prompt)
        return out if out else default
    return default
