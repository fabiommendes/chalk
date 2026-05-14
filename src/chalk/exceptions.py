from __future__ import annotations

import enum
import sys
from typing import NoReturn

import rich

from .models import Any


class Error(enum.Enum):
    """Enumeration of error codes for Chalk exceptions."""

    CONFIG_NOT_FOUND = "CONFIG_NOT_FOUND"
    ROSTER_NOT_FOUND = "ROSTER_NOT_FOUND"
    MULTIPLE_ROSTERS_FOUND = "MULTIPLE_ROSTERS_FOUND"
    INVALID_CONFIG = "INVALID_CONFIG"
    BAD_ROSTER = "BAD_ROSTER"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FIELD = "INVALID_FIELD"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"

    def throw(self, message: str | None = None) -> NoReturn:
        """
        Raise a ChalkError with this error code and an optional message.
        """

        raise self.exception(message)

    def exception(self, message: str | None = None) -> ChalkError:
        """
        Create a ChalkError with this error code and an optional message.
        """

        return ChalkError(self, message)

    def __call__(self, message: str | None = None) -> ChalkError:
        """
        Allow the enum member to be called directly to create a ChalkError.
        """

        return self.exception(message)


class ChalkError(Exception):
    """Base class for all user-facing Chalk exceptions."""

    def __init__(self, code: Error, message: str | None = None, data: Any = None):
        super().__init__(code, message)
        self.code = code
        self.message = message
        self.data = data

    def print(self):
        """Print the error message to the console."""

        if self.message:
            rich.print(f"[bold red]Error:[/] {self.message}", file=sys.stderr)
            return

        match self.code:
            case Error.CONFIG_NOT_FOUND:
                rich.print(
                    "[bold red]Error:[/] Could not find chalk.toml configuration file. Are you sure you're in a Chalk project?",
                    file=sys.stderr,
                )
            case Error.ROSTER_NOT_FOUND:
                rich.print(
                    "[bold red]Error:[/] Could not find roster file. Are you sure you're in a Chalk project?",
                    file=sys.stderr,
                )
            case Error.MULTIPLE_ROSTERS_FOUND:
                rich.print(
                    "[bold red]Error:[/] Multiple roster files found",
                    file=sys.stderr,
                )
            case Error.INVALID_CONFIG:
                rich.print(
                    "[bold red]Error:[/] Invalid chalk.toml configuration file",
                    file=sys.stderr,
                )
            case Error.BAD_ROSTER:
                rich.print(
                    "[bold red]Error:[/] Invalid roster file",
                    file=sys.stderr,
                )
            case Error.MISSING_FIELD:
                rich.print(
                    "[bold red]Error:[/] Missing required field in configuration or roster",
                    file=sys.stderr,
                )
            case Error.INVALID_FIELD:
                rich.print(
                    "[bold red]Error:[/] Invalid value for field in configuration or roster",
                    file=sys.stderr,
                )
