from typing import Any

from ..table import Table
from . import GeneratedColumns, PluginMethods


def plugin() -> PluginMethods:
    return {
        "extract_columns": extract_columns,
    }


def extract_columns(table: Table[Any]) -> GeneratedColumns:
    data: list[dict[str, Any]] = []
    for row in table.iter_rows():
        email = row.get("email")
        data.append(
            {
                "id": email.rpartition("@")[0]
                if isinstance(email, str) and "@" in email
                else None
            }
        )

    return {
        "data": Table(data),
        "used": {"email"},
    }
