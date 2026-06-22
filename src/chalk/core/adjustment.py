from __future__ import annotations

import copy
import re
from decimal import Decimal
from typing import Iterable, Literal, TypeGuard, cast, get_args, overload

import opt

from ..types import Numeric, to_decimal
from ..util.parsing import Parsed, read_number, read_parens

REASON = re.compile(r"([a-z_]+)\s+")


AdjustmentReason = Literal[
    "points_given",
    "cancelled",
    "regraded",
    "late",
    "early",
    None,
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
    def reason(self) -> AdjustmentReason:
        return self._reason

    @property
    def description(self) -> str | None:
        return self._description

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
        return Adjustment(
            override=value, reason="points_given", description=description
        )

    @classmethod
    def late_pc(cls, percentage: Numeric, description: str | None = None) -> Adjustment:
        """
        Create an adjustment that multiplies the grade by (1 - percentage) with
        reason "late".
        """
        return Adjustment(
            relative=1 - Decimal(percentage) / Decimal(100),
            reason="late",
            description=description,
        )

    @classmethod
    def early_pc(
        cls, percentage: Numeric, description: str | None = None
    ) -> Adjustment:
        """
        Create an adjustment that multiplies the grade by (1 + percentage) with
        reason "early".
        """
        return Adjustment(
            relative=1 + Decimal(percentage) / Decimal(100),
            reason="early",
            description=description,
        )

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

    @overload
    def __init__(self, value: Numeric | str, /) -> None: ...

    @overload
    def __init__(
        self,
        *,
        relative: Numeric = 1,
        reason: AdjustmentReason = None,
        description: str | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        absolute: Numeric = 0,
        reason: AdjustmentReason = None,
        description: str | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        override: Numeric,
        reason: AdjustmentReason = None,
        description: str | None = None,
    ) -> None: ...

    def __init__(
        self,
        value: Numeric | str | None = None,
        *,
        relative: Numeric = 1,
        absolute: Numeric = 0,
        override: Numeric | None = None,
        reason: AdjustmentReason = None,
        description: str | None = None,
    ) -> None:
        self._reason: AdjustmentReason = reason
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
            self._override = Decimal(override)
        else:
            self._relative = Decimal(relative)
            self._absolute = Decimal(absolute)

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
                    reason=opt.coalesce(self.reason, other.reason),
                    description=opt.coalesce(self.description, other.description),
                )
                new._relative = a * aa
                new._absolute = b * aa + bb
                return new

    def __hash__(self) -> int:
        return hash((self.relative, self.absolute, self.override, self.reason))

    def apply(self, grade: Numeric) -> Decimal:
        """
        Apply this adjustment to the given grade and return the result.
        """
        if self.override is not None:
            return self.override
        return Decimal(grade) * self.relative + self.absolute

    def represent(self, value: Numeric) -> str:
        """
        Return a string representation of this adjustment when applied to the
        given grade.
        """

        data = ""
        if self.reason is not None:
            data += f"{self.reason}: "

        source = to_decimal(value)
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


def is_valid_reason(src: str) -> TypeGuard[AdjustmentReason]:
    """
    Check if the given string is a valid override reason.
    """
    return src in get_args(AdjustmentReason)


def apply_chain(grade: Numeric, adjustments: Iterable[Adjustment]) -> Decimal:
    """
    Apply a chain of adjustments to the given grade and return the result.
    """
    grade = Decimal(grade)
    for adj in adjustments:
        grade = adj.apply(grade)
    return grade


def parse(src: str) -> tuple[Adjustment, Decimal]:
    """
    Parse a string that could be produced from Adjustment.represent() back into
    an Adjustment and the original grade.
    """

    parsed = read(src)
    if parsed.remaining:
        raise ValueError(f"Unexpected adjustment string: {src!r}")
    return parsed.value


def read(src: str) -> Parsed[tuple[Adjustment, Decimal]]:
    """
    Read an adjustment from a string representation.

    Return the remaining string, the parsed adjustment, and the original grade
    as a Decimal or raise ValueError if the string is not a valid adjustment
    representation.
    """
    rest = src.lstrip()
    reason: AdjustmentReason | None = None
    description: str | None = None

    if m := REASON.match(rest):
        if not is_valid_reason(m.group(1)):
            raise ValueError(f"Invalid adjustment reason: {m.group(1)!r}")
        reason = cast(AdjustmentReason, m.group(1))
        rest = rest[m.end() :]

    rest, number = read_number(rest)
    rest = rest.lstrip()

    if rest.startswith("+"):
        rest, value = read_number(rest[1:])
        if rest.startswith("%"):
            rest = rest[1:]
            value = value / 100 + 1
            adj = Adjustment(relative=value, reason=reason, description=description)
        else:
            adj = Adjustment(absolute=value, reason=reason, description=description)

    elif rest.startswith("-"):
        rest, value = read_number(rest[1:])
        if rest.startswith("%"):
            rest = rest[1:]
            value = 1 - value / 100
            adj = Adjustment(relative=value, reason=reason, description=description)
        else:
            adj = Adjustment(absolute=-value, reason=reason, description=description)

    elif rest.startswith("=>"):
        rest, value = read_number(rest[2:])
        adj = Adjustment(override=value, reason=reason, description=description)
    else:
        raise ValueError(f"Invalid adjustment format: {src.removesuffix(rest)!r}...")

    if rest.startswith("("):
        rest, description = read_parens(rest)
        adj = adj.describe(description)

    return Parsed(rest, (adj, number))
