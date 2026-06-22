from __future__ import annotations

import enum
from dataclasses import dataclass, field
from functools import total_ordering
from typing import Any, Iterable, Literal, Self, cast

import rich

type IssueLevelLike = (
    IssueLevel
    | Literal["critical", "error", "warning", "all"]
    | list[Literal["critical", "error", "warning", "all"]]
)


@dataclass(frozen=True)
@total_ordering
class Issue[Code = str, Scope = str, Target = Any]:
    """
    An issue with in the system that may prevent correct behavior.

    The severity system works as follows:

    - Critical issues prevent correct functionality in all scopes.
    - Error issues prevent correct functionality in the specified scopes, but
      not necessarily all scopes.
    - Warning issues do not prevent correct functionality, but indicate
      potential problems that should be addressed.
    """

    @classmethod
    def critical(
        cls,
        code: Code,
        message: str | None = None,
        scopes: Iterable[Scope] | None = None,
    ) -> Issue[Code, Scope]:
        """
        Create a critical issue with the given code and message.
        """
        return cls(
            code,
            message,
            severity=IssueLevel.CRITICAL,
            scopes=frozenset(scopes or ()),
        )

    @classmethod
    def error(
        cls,
        code: Code,
        message: str | None = None,
        scopes: Iterable[Scope] | None = None,
    ) -> Issue[Code, Scope]:
        """
        Create an error issue with the given code and message.
        """
        return cls(
            code,
            message,
            severity=IssueLevel.ERROR,
            scopes=frozenset(scopes or ()),
        )

    @classmethod
    def warning(
        cls,
        code: Code,
        message: str | None = None,
        scopes: Iterable[Scope] | None = None,
    ) -> Issue[Code, Scope]:
        """
        Create a warning issue with the given code and message.
        """
        return cls(
            code,
            message,
            severity=IssueLevel.WARNING,
            scopes=frozenset(scopes or ()),
        )

    code: Code
    message: str | None = None
    severity: IssueLevel = field(default_factory=lambda: IssueLevel.ERROR)
    scopes: frozenset[Scope] = field(default_factory=frozenset)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Issue):
            return NotImplemented
        return (
            self.code == other.code
            and self.message == other.message
            and self.severity == other.severity
            and self.scopes == other.scopes
        )

    def __lt__(self, other: Issue) -> bool:
        if not isinstance(other, Issue):
            return NotImplemented

        return self._as_ord_tuple() < other._as_ord_tuple()

    def _as_ord_tuple(self) -> tuple[Any, ...]:
        """
        Tuple representation for lexicographic ordering.
        """
        return (
            self.severity,
            self.code,
            sorted(cast(Any, self.scopes)),
            self.message or "",
        )

    def with_scopes(self, scopes: Iterable[Scope]) -> Self:
        """
        Return a new issue with the given scope added.
        """
        scopes = frozenset(scopes)
        if scopes.issubset(self.scopes):
            return self

        return self.__class__(
            code=self.code,
            message=self.message,
            severity=self.severity,
            scopes=self.scopes | scopes,
        )

    def display(self, rich_text: bool = True) -> None:
        """
        Display this issue to the user in a human-readable format.
        """
        rich.print(render_severity(self.severity, rich_text), end="")
        if self.scopes and rich_text:
            data = "|".join(map(str, self.scopes))
            rich.print("[bold]\\[{}][/]".format(data), end=": ")
        rich.print(f"{self.code}")

        if self.message and rich_text:
            rich.print(f"  [italic]{self.message}[/]")
        else:
            rich.print(f"  {self.message}")


class IssueLevel(enum.IntFlag):
    CRITICAL = 1
    ERROR = 2
    WARNING = 4
    ALL = CRITICAL | ERROR | WARNING

    @classmethod
    def construct(cls, value: IssueLevelLike) -> IssueLevel:
        if isinstance(value, IssueLevel):
            return value
        if isinstance(value, str):
            value = [value]
        level = cls(0)
        for v in value:
            match v.lower():
                case "critical":
                    level |= cls.CRITICAL
                case "error":
                    level |= cls.ERROR
                case "warning":
                    level |= cls.WARNING
                case "all":
                    level |= cls.ALL
                case _:
                    raise ValueError(f"Invalid issue level: {v}")
        return level


def render_severity(severity: IssueLevel | None, rich_text: bool = True) -> str:
    """
    Get a human-readable string representation of an issue severity level.
    """
    match severity:
        case IssueLevel.CRITICAL:
            return fmt("Critical", "bold red", rich_text)
        case IssueLevel.ERROR:
            return fmt("Error", "bold red", rich_text)
        case IssueLevel.WARNING:
            return fmt("Warning", "bold yellow", rich_text)
        case _:
            return fmt("Info", "bold blue", rich_text)


def fmt(obj: Any, style: str, rich_text: bool = True) -> str:
    """
    Format an object for display in an error message or issue report.
    """
    if rich_text:
        return f"[{style}]{obj}[/]"
    else:
        return str(obj)
