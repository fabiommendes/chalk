from functools import partial
from typing import Any, Callable, NotRequired, TypedDict

from ..table import Table

type Plugin = Callable[[], PluginMethods]
type ExtractColumnsMethod = Callable[[Table[Any]], GeneratedColumns]


class PluginMethods(TypedDict):
    extract_columns: NotRequired[ExtractColumnsMethod]


class GeneratedColumns(TypedDict):
    data: Table[Any]
    used: NotRequired[set[str] | list[str]]


def merge_plugins(plugins: list[PluginMethods]) -> PluginMethods:
    """
    Merge multiple plugins into a single PluginMethods dictionary.
    """
    merged: PluginMethods = {}

    # Extract methods
    if any("extract_columns" in plugin for plugin in plugins):
        merged["extract_columns"] = partial(extract_columns_method, plugins)

    return merged


def extract_columns_method(
    plugins: list[PluginMethods], data: Table[Any]
) -> GeneratedColumns:
    """
    Create a global "extract_columns" method from a sequence of plugins.
    """
    # used: set[str] = set()
    # table: list[Any] = []
    # generated: GeneratedColumns = {"data": table, "used": used}

    # for plugin in plugins:
    #     extract_method = plugin.get("extract_columns")
    #     if extract_method is None:
    #         continue

    #     extra = extract_method(data)
    #     table = merge(table, extra["data"])
    #     used.update(extra.get("used", set()))

    # if not used:
    #     del generated["used"]
    # generated["data"] = table
    # return generated
    raise NotImplementedError
