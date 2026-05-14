from typing import Callable, Mapping, overload

import rich
import rich.measure


@overload
def clean_data(data: dict, /) -> dict: ...


@overload
def clean_data(data: list, /) -> list: ...


def clean_data(data):
    """
    Clean data by removing any keys with None values.
    """
    if isinstance(data, list):
        return [clean_data(item) for item in data]
    elif isinstance(data, dict):
        return {k: clean_data(v) for k, v in data.items() if v is not None}
    else:
        return data


def clean_table(
    data: list[dict],
    *,
    keep: set[str] | None = None,
    remove: set[str] | None = None,
) -> list[dict]:
    """
    Clean the table by removing empty columns.

    Args:
        data: The table data as a list of dictionaries.
        keep: A set of column names to always keep even if they are empty.
        remove: A set of column names to remove even if they are not empty.
    """
    if keep is None:
        keep = active_columns(data)
    else:
        keep = active_columns(data) | keep
    keep = keep - (remove or set())

    return [{k: v for k, v in item.items() if k in keep} for item in data]


def active_columns[K, V](data: list[dict[K, V | None]]) -> set[K]:
    """
    Get the active columns from the data by returning the keys that have
    non-None values.
    """
    columns: set[K] = set()
    for item in data:
        columns.update(k for k, v in item.items() if v is not None)
    return columns


def column_sizes[K, V](data: list[dict[K, V | None]]) -> dict[K, int]:
    """
    Get the column sizes from the data by returning a dictionary of the
    maximum length of the values for each key.
    """
    sizes: dict[K, int] = {}
    for item in data:
        for k, v in item.items():
            size = len(str(v)) if v is not None else 0
            sizes[k] = max(sizes.get(k, 0), size)
    return sizes


def select_columns[K, V](
    data: list[dict[K, V]], columns: set[K] | Callable[[K], bool]
) -> list[dict[K, V]]:
    """
    Select the columns from the data by returning a list of dictionaries
    containing only the keys that are in the given set or satisfy the given
    predicate.

    Args:
        data: The table data as a list of dictionaries.
        columns: A set of column names to select or a predicate function that
            takes a column name and returns True if it should be selected.
    """
    if not callable(columns):
        columns = columns.__contains__
    return [{k: v for k, v in item.items() if columns(k)} for item in data]


def merge_columns[K, V](
    a: list[dict[K, V]],
    b: list[dict[K, V]],
    /,
) -> list[dict[K, V]]:
    """
    Merge the columns from two lists of dictionaries by returning a new list of
    dictionaries containing the union of the keys from both lists.

    The values from the second list will overwrite the values from the first
    list if there are duplicate keys.
    """
    return [{**item_a, **item_b} for item_a, item_b in zip(a, b)]


def render_table[K, V](
    data: list[dict[K, V | None]],
    max_size: None | int | dict[K, int] = None,
    styles: None | dict[K, str] = None,
    names: None | dict[K, str] = None,
    align: None | dict[K, str] = None,
    empty: str = "[b yellow]Warning:[/] no data to display!",
):
    """
    Render the data as a table by using the column sizes to format the
    values.
    """
    if not data:
        rich.print(empty)
        return

    columns = active_columns(data)

    sizes = column_sizes(data)
    if isinstance(max_size, dict):
        sizes = {k: min(sizes.get(k, 0), max_size.get(k, 0)) for k in columns}
    elif isinstance(max_size, int):
        sizes = {k: min(sizes.get(k, 0), max_size) for k in columns}

    # Render the header
    names = names or {}
    align = align or {}
    for i, col in enumerate(columns):
        if i > 0:
            rich.print(" | ", end="")

        name = str(names.get(col, str(col).upper()))
        name = align_text(name, sizes[col], align=align.get(col, "left"))

        rich.print(f"[b]{name}[/]", end="")

    # Render the rows
    styles = styles or {}
    for item in data:
        rich.print()
        for i, col in enumerate(columns):
            if i > 0:
                rich.print(" | ", end="")

            value = str(item.get(col, ""))
            value = trucate_text(value, sizes[col])
            value = align_text(value, sizes[col], align=align.get(col, "left"))

            style = styles.get(col, "")
            if style:
                rich.print(f"[{style}]{value}[/]", end="")
            else:
                rich.print(value, end="")


def trucate_text(text: str, max_length: int | None) -> str:
    """
    Truncate the text to the maximum length by adding "..." at the end if
    the text is longer than the maximum length.
    """
    if max_length is None:
        return text
    if len(text) <= max_length:
        return text
    else:
        return text[: max_length - 3] + "..."


def align_text(text: str, width: int, align: str = "left") -> str:
    """
    Align the text to the left, right, or center by adding spaces at the
    beginning or end of the text.
    """
    if align == "left":
        return text.ljust(width)
    elif align == "right":
        return text.rjust(width)
    elif align == "center":
        return text.center(width)
    else:
        raise ValueError(f"Invalid alignment: {align}")


def sorted_by_key(data: list[dict], key: str, reverse: bool = False) -> list[dict]:
    """
    Sort the data by the given key by using the built-in sorted function.
    """
    return sorted(data, key=lambda d: d[key], reverse=reverse)


def maybe_map[T, R](fn: Callable[[T], R], value: T | None) -> R | None:
    """
    Apply the function to the value if it is not None, otherwise return None.
    """
    return None if value is None else fn(value)


def rename_columns[K, V](
    data: list[dict[K, V]], transform: Mapping[K, K]
) -> list[dict[K, V]]:
    """
    Rename the columns of the data by the transformation in the dictionary.
    """
    return [{transform.get(k, k): v for k, v in item.items()} for item in data]


HEURISTIC_MAP_NORMALIZERS = [str.lower, lambda s: "".join(c for c in s if c.isalnum())]


def heuristic_map(columns: set[str], expected: set[str]) -> dict[str, str]:
    """
    Heuristically map the columns to the expected columns by using a simple
    string similarity metric.
    """

    mapping: dict[str, str] = {}

    # First try exact matches
    exact = columns.intersection(expected)
    mapping.update({col: col for col in exact})

    columns -= exact
    expected -= exact

    # Then try using some normalization heuristics
    if columns:
        for normalizer in HEURISTIC_MAP_NORMALIZERS:
            columns_ = {normalizer(col): col for col in columns}
            expected_ = {normalizer(col): col for col in expected}
            exact = set(columns_.keys()).intersection(expected_.keys())
            mapping.update({columns_[col]: expected_[col] for col in exact})
            columns -= {columns_[col] for col in exact}
            expected -= {expected_[col] for col in exact}

    # Finally, try a more expensive similarity metric
    if columns:
        import difflib

        for col in columns:
            best_match = difflib.get_close_matches(col, expected, n=1)
            if best_match:
                mapping[col] = best_match[0]
                expected.remove(best_match[0])

    return mapping
