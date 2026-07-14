from __future__ import annotations

import copy
import re
from decimal import Decimal
from typing import Iterable, Literal, TypeGuard, cast, get_args, overload

import opt

from ..numeric import Numeric, add, mul, to_decimal
from ..util.parsing import Parsed, read_number, read_parens

REASON = re.compile(r"([a-z_]+)\s+")


AdjustmentReason = Literal[
    "points_given",
    "cancelled",
    "regraded",
    "late",
    "early",
]


#
# Adjustments to the grade
#
class Adjustment:
    """
    Describes some arbitrary adjustment to a grade, such as a relative or
    absolute change, or an override.
    """

    @property
    def relative(self) -> Decimal:
        """
        The relative multiplier of this adjustment. For example, a relative
        adjustment of 0.5 will halve the grade, while a relative adjustment of
        1.5 will increase the grade by 50%.
        """
        return self._relative

    @property
    def absolute(self) -> Decimal:
        return self._absolute

    @property
    def override(self) -> Decimal | None:
        return self._override

    @property
    def reason(self) -> AdjustmentReason | None:
        return self._reason

    @property
    def description(self) -> str | None:
        return self._description

    @property
    def method(
        self,
    ) -> Literal["relative", "absolute", "overriden", "comment", "affine"]:
        """
        The method used for this adjustment.

        Comment is a special case of relative adjustment with relative=1 and
        absolute=0.
        """
        if self.override is not None:
            return "overriden"
        if self.relative == 1 and self.absolute == 0:
            return "comment"
        elif self.relative != 1:
            return "relative"
        elif self.relative == 1:
            return "absolute"
        else:
            return "affine"

    #
    # Utility constructors for common cases
    #
    @classmethod
    def regraded(cls, value: Numeric, description: str | None = None) -> Adjustment:
        """
        Create an adjustment that overrides the grade with the given value and
        reason "regraded".
        """
        return Adjustment(override=value, reason="regraded", description=description)

    @classmethod
    def cancelled(cls, description: str | None = None) -> Adjustment:
        """
        Create an adjustment that sets the grade to 0 with reason "cancelled".
        """
        return Adjustment(override=0, reason="cancelled", description=description)

    @classmethod
    def points_given(cls, value: Numeric, description: str | None = None) -> Adjustment:
        """
        Create an adjustment that overrides the grade with the given value and reason "points_given".
        """
        return Adjustment(override=value, reason="points_given", description=description)

    @classmethod
    def late_pc(
        cls, percentage: Decimal | int | float, description: str | None = None
    ) -> Adjustment:
        """
        Create an adjustment that multiplies the grade by (1 - percentage) with
        reason "late".
        """
        return Adjustment(
            relative=1 - Decimal(percentage) / 100,
            reason="late",
            description=description,
        )

    @classmethod
    def early_pc(
        cls, percentage: Decimal | int | float, description: str | None = None
    ) -> Adjustment:
        """
        Create an adjustment that multiplies the grade by (1 + percentage) with
        reason "early".
        """
        return Adjustment(
            relative=1 + Decimal(percentage) / 100,
            reason="early",
            description=description,
        )

    @classmethod
    def deserialize(cls, src: str) -> Adjustment:
        """
        Deserialize a string representation of an adjustment back into an
        Adjustment object.
        """
        adj, _ = parse(src, _parse_x=True)
        return adj

    @overload
    def __init__(self, value: Numeric | str, /) -> None: ...

    @overload
    def __init__(
        self,
        *,
        relative: Numeric = 1,
        reason: AdjustmentReason | None = None,
        description: str | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        absolute: Numeric = 0,
        reason: AdjustmentReason | None = None,
        description: str | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        override: Numeric,
        reason: AdjustmentReason | None = None,
        description: str | None = None,
    ) -> None: ...

    def __init__(
        self,
        value: Numeric | str | None = None,
        *,
        relative: Numeric = 1,
        absolute: Numeric = 0,
        override: Numeric | None = None,
        reason: AdjustmentReason | None = None,
        description: str | None = None,
    ) -> None:
        self._reason: AdjustmentReason | None = reason
        self._description = description
        self._override = None
        if isinstance(value, str) and value.endswith("%"):
            data = Decimal(value.removesuffix("%").strip())
            self._relative = data / 100 + 1
            self._absolute = Decimal(0)
        elif value is not None:
            self._relative = Decimal(1)
            self._absolute = to_decimal(value)
        elif override is not None:
            self._relative = Decimal(1)
            self._absolute = Decimal(0)
            self._override = to_decimal(override)
        else:
            self._relative = to_decimal(relative)
            self._absolute = to_decimal(absolute)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Adjustment):
            return (
                self.relative == other.relative
                and self.absolute == other.absolute
                and self.override == other.override
                and self.reason == other.reason
            )
        return NotImplemented

    def __repr__(self) -> str:
        args = []
        if self.reason is not None:
            args.append(f"reason={self.reason!r}")
        if self.description is not None:
            args.append(f"description={self.description!r}")
        if self.override is not None:
            args.append(f"override={self.override}")
        elif self.relative != 1:
            args.append(f"relative={self.relative}")
        elif self.absolute != 0:
            args.append(f"absolute={self.absolute}")
        return f"Adjustment({', '.join(args)})"

    def __str__(self) -> str:
        return self._represent_with_value("x")

    def __rshift__(self, other: Adjustment) -> Adjustment:
        if not isinstance(other, Adjustment):
            return NotImplemented

        match (other.method, self.method):
            case ("comment", _) | (_, "override"):
                return other
            case (_, "comment"):
                return self
            case ("relative", "relative"):
                return Adjustment(
                    relative=self.relative * other.relative,
                    reason=other.reason or self.reason,
                    description=other.description or self.description,
                )
            case ("absolute", "absolute"):
                return Adjustment(
                    absolute=self.absolute + other.absolute,
                    reason=other.reason or self.reason,
                    description=other.description or self.description,
                )
            case ("override", _):
                return Adjustment(
                    override=self.apply(self.override),
                    reason=other.reason or self.reason,
                    description=other.description or self.description,
                )
            case _:
                a = self.relative
                b = self.absolute
                aa = other.relative
                bb = other.absolute

                new = Adjustment(
                    absolute=0,
                    reason=opt.coalesce(self.reason, other.reason),  # pyright: ignore[reportArgumentType]
                    description=opt.coalesce(self.description, other.description),
                )
                new._relative = a * aa
                new._absolute = b * aa + bb
                return new

    def __hash__(self) -> int:
        return hash((self.relative, self.absolute, self.override, self.reason))

    def __call__(self, grade: Numeric) -> Numeric:
        return self.apply(grade)

    def apply(self, grade: Numeric) -> Numeric:
        """
        Apply this adjustment to the given grade and return the result.
        """
        if self.override is not None:
            return self.override
        return add(mul(grade, self.relative), self.absolute)

    def represent(self, value: Numeric) -> str:
        """
        Return a string representation of this adjustment when applied to the
        given grade.
        """
        return self._represent_with_value(value)

    def _represent_with_value(self, value: Numeric | str) -> str:
        # We separate those two cases to implement __str__

        data = ""
        if self.reason is not None:
            data += f"{self.reason}: "

        source = "x" if value == "x" else to_decimal(value)
        match self.method:
            case "comment":
                data += str(source)
            case "relative":
                pc = self.relative_percentage()
                sign = "+" if pc >= 0 else "-"
                data += f"{source} {sign}{abs(pc)}%"
            case "absolute":
                sign = "+" if self.absolute >= 0 else "-"
                data += f"{source} {sign}{abs(self.absolute)}"
            case "overriden":
                data += f"{source} => {self.override}"

        if self.description is not None:
            data += f" ({self.description})"

        return data

    def relative_percentage(self) -> Decimal:
        """
        Return the percentage change of this adjustment when applied to the
        given grade.
        """
        return (self.relative - 1) * 100

    def describe(self, description: str | None) -> Adjustment:
        """
        Return a new adjustment with the same properties as this one but with
        the given description.
        """
        new = copy.copy(self)
        new._description = description
        return new

    def serialize(self) -> str:
        """
        Serialize this adjustment to a string.
        """
        return str(self)


def is_valid_reason(src: str) -> TypeGuard[AdjustmentReason]:
    """
    Check if the given string is a valid override reason.
    """
    return src in get_args(AdjustmentReason)


def apply_chain(grade: Numeric, adjustments: Iterable[Adjustment]) -> Numeric:
    """
    Apply a chain of adjustments to the given grade and return the result.
    """
    for adj in adjustments:
        grade = adj.apply(grade)
    return grade


def parse(src: str, *, _parse_x: bool = False) -> tuple[Adjustment, Decimal]:
    """
    Parse a string that could be produced from Adjustment.represent() back into
    an Adjustment and the original grade.
    """

    parsed = read(src, _parse_x=_parse_x)
    if parsed.remaining:
        raise ValueError(f"Unexpected adjustment string: {src!r}")
    return parsed.value


def read(src: str, *, _parse_x: bool = False) -> Parsed[tuple[Adjustment, Decimal]]:
    """
    Read an adjustment from a string representation.

    Return the remaining string, the parsed adjustment, and the original grade
    as a Decimal or raise ValueError if the string is not a valid adjustment
    representation.
    """
    unread = src.lstrip()
    reason: AdjustmentReason | None = None
    description: str | None = None

    if m := REASON.match(unread):
        if not is_valid_reason(m.group(1)):
            raise ValueError(f"Invalid adjustment reason: {m.group(1)!r}")
        reason = cast(AdjustmentReason, m.group(1))
        unread = unread[m.end() :]

    if _parse_x and unread.startswith("x"):
        unread = unread[1:].lstrip()
        number = Decimal(0)
    else:
        unread, number = read_number(unread)
    unread = unread.lstrip()

    if unread.startswith("+"):
        unread, value = read_number(unread[1:])
        if unread.startswith("%"):
            unread = unread[1:]
            value = value / 100 + 1
            adj = Adjustment(relative=value, reason=reason, description=description)
        else:
            adj = Adjustment(absolute=value, reason=reason, description=description)

    elif unread.startswith("-"):
        unread, value = read_number(unread[1:])
        if unread.startswith("%"):
            unread = unread[1:]
            value = 1 - value / 100
            adj = Adjustment(relative=value, reason=reason, description=description)
        else:
            adj = Adjustment(absolute=-value, reason=reason, description=description)

    elif unread.startswith("=>"):
        unread, value = read_number(unread[2:])
        adj = Adjustment(override=value, reason=reason, description=description)
    else:
        raise ValueError(f"Invalid adjustment format: {src.removesuffix(unread)!r}...")

    if unread.startswith("("):
        unread, description = read_parens(unread)
        adj = adj.describe(description)

    return Parsed(unread, (adj, number))
