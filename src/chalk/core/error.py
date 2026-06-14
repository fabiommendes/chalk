from __future__ import annotations

import enum
import sys
from typing import Any, NoReturn, cast

import rich

ARE_YOU_SURE_MSG = "Are you sure you're in a Chalk project?"


class ChalkError[E: BaseEnum](Exception):
    """Base class for all user-facing Chalk exceptions."""

    @property
    def reason(self) -> E:
        """The reason for this error, as an Error enum member."""
        return cast(E, self.args[0])

    @property
    def message(self) -> str | None:
        """An optional error message providing more details about the error."""
        return self.args[1] if len(self.args) > 1 else None

    @property
    def data(self) -> Any:
        """Any additional data associated with this error."""
        return self.args[2] if len(self.args) > 2 else None

    def __init__(self, reason: E, message: str | None = None, data: Any = None):
        super().__init__(reason, message, data)

    def print(self) -> None:
        """Print the error message to the console."""

        if self.message:
            rich.print(f"[bold red]Error:[/] {self.message}", file=sys.stderr)
            return
        else:
            rich.print(f"[bold red]Error:[/] {self.reason.value}", file=sys.stderr)


class BaseEnum(enum.StrEnum):
    """
    A base class for enums that can be called to create a ChalkError with the enum member as the reason.
    """

    def _exception_type(self) -> type[ChalkError[Any]]:
        """
        Get the type of ChalkError that should be created when this enum member is called.
        """
        return ChalkError

    def __call__(self, message: str | None = None, data: Any = None) -> ChalkError[Any]:
        """
        Allow the enum member to be called directly to create a ChalkError.
        """
        return self.exception(message)

    def exception(
        self,
        message: str | None = None,
        data: Any = None,
    ) -> ChalkError[Any]:
        """
        Create a ChalkError with this error code and an optional message.
        """
        exception_type = self._exception_type()
        return exception_type(self, message, self.validate_data(data))

    def throw(self, message: str | None = None) -> NoReturn:
        """
        Raise a ChalkError with this error code and an optional message.
        """

        raise self.exception(message)

    def message(self, message: str | None = None) -> str:
        """
        Get the error message for this error code, optionally including additional details from the message parameter.
        """
        return self.value if message is None else f"{self.name}: {message}"

    def validate_data(self, data: Any) -> Any:
        """
        Validate any additional data associated with this error code. By default, just returns the data unmodified.
        """
        return data


class CannotGrade(BaseEnum):
    """
    An enumeration of reasons why a grade cannot be computed for a given question/answer.
    """


class SystemError(BaseEnum):
    """
    Enumeration of error codes for global Chalk exceptions.
    """

    CONFIG_NOT_FOUND = f"Could not find chalk.toml. {ARE_YOU_SURE_MSG}"
    ROSTER_NOT_FOUND = f"Roster file not found. {ARE_YOU_SURE_MSG}"
    MULTIPLE_ROSTERS_FOUND = "Multiple roster files found"
    INVALID_CONFIG = "Invalid chalk.toml configuration file"
    BAD_ROSTER = "Invalid roster file"
    MISSING_FIELD = "Missing required field in configuration or roster"
    INVALID_FIELD = "Invalid value for field in configuration or roster"
    RESOURCE_NOT_FOUND = "Requested resource not found"
