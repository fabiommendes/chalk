"""
Basic types and protocols used throughout the Chalk codebase.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar

if TYPE_CHECKING:
    pass

_T_contra = TypeVar("_T_contra", contravariant=True)

type JSON = dict[str, Any] | list[Any] | str | int | float | bool | None


class SupportsDunderLT(Protocol[_T_contra]):
    def __lt__(self, other: _T_contra, /) -> bool: ...


class SupportsDunderGT(Protocol[_T_contra]):
    def __gt__(self, other: _T_contra, /) -> bool: ...


type SupportsRichComparison[_T_contra] = (
    SupportsDunderLT[_T_contra] | SupportsDunderGT[_T_contra]
)


class ReadOnly[T](Protocol):
    """
    A protocol for read-only descriptors.
    """

    def __get__(self, instance: object, owner: type) -> T: ...


class Displayable(Protocol):
    def display(self) -> None:
        """
        Display the object in the console in a human-readable format.
        """
        ...
