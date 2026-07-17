from __future__ import annotations

from decimal import Decimal
from typing import Any

type JSONAtom = float | int | str | Decimal | None
type JSON = JSONAtom | bool | dict[str, Any] | list[Any]
