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

    default = Path.cwd().name

    if get_interactivity(interactive):
        return Prompt.ask("Classroom name", default=default)

    return default


def get_env_teacher(value: str | None, interactive: bool | None = None) -> str:
    """
    Use either the given value or compute the default teacher name from the environment.
    """
    if value is not None:
        return value

    default = os.environ.get("CHALK_USER") or os.getlogin()

    if get_interactivity(interactive):
        return Prompt.ask("Teacher name", default=default)

    return default


def get_interactivity(value: bool | None) -> bool:
    """
    Determine whether to use interactive prompts based on the given value and the environment.
    """
    if value is not None:
        return value

    return os.isatty(0) and os.isatty(1) and os.environ.get("CHALK_INTERACTIVE", "1") == "1"


@overload
def ask_optional_string(
    prompt: str,
    value: str | None = None,
    *,
    default: str,
    interactive: bool | None = None,
    style: str | None = "bold",
) -> str: ...


@overload
def ask_optional_string(
    prompt: str,
    value: str | None = None,
    *,
    default: str | None = None,
    interactive: bool | None = None,
    style: str | None = "bold",
) -> str | None: ...


def ask_optional_string(
    prompt: str,
    value: str | None = None,
    *,
    default: str | None = None,
    interactive: bool | None = None,
    style: str | None = "bold",
) -> str | None:
    """
    Ask the user for a value using a prompt, with an optional default value.
    """
    if style is not None:
        prompt = f"[{style}]{prompt}[/]"
    if value is not None:
        return value
    elif get_interactivity(interactive) and default is not None:
        out = Prompt.ask(prompt, default=default)
        return out if out else default
    elif get_interactivity(interactive):
        out = Prompt.ask(prompt)
        return out if out else default
    return default
