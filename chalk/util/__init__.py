from collections import defaultdict
from typing import Any, Callable, Iterable, Mapping, overload


@overload
def clean_data[K, V](data: dict[K, V | None], /) -> dict[K, V]: ...
@overload
def clean_data[K, V](data: list[dict[K, V | None]], /) -> list[dict[K, V]]: ...
@overload
def clean_data[K, V](data: set[dict[K, V | None]], /) -> set[dict[K, V]]: ...
@overload
def clean_data[K, V](data: tuple[dict[K, V | None]], /) -> tuple[dict[K, V]]: ...


def clean_data(data: Any) -> Any:
    """
    Clean data by removing any keys with None values.
    """
    if isinstance(data, list):
        return [clean_data(item) for item in data]
    if isinstance(data, set):
        return {clean_data(item) for item in data}
    if isinstance(data, tuple):
        return tuple(clean_data(item) for item in data)
    elif isinstance(data, dict):
        return {k: clean_data(v) for k, v in data.items() if v is not None}
    else:
        return data


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


HEURISTIC_MAP_NORMALIZERS: list[Callable[[str], str]] = [
    str.lower,
    lambda s: "".join(c for c in s if c.isalnum()),
]


def heuristic_map(names: set[str], expected: set[str]) -> dict[str, str]:
    """
    Heuristically map a set of names to the expected names by using a simple
    string similarity metric.
    """

    mapping: dict[str, str] = {}

    # First try exact matches
    exact = names.intersection(expected)
    mapping.update({name: name for name in exact})

    names -= exact
    expected -= exact

    # Then try using some normalization heuristics
    if names:
        for normalizer in HEURISTIC_MAP_NORMALIZERS:
            names_ = {normalizer(name): name for name in names}
            expected_ = {normalizer(name): name for name in expected}
            exact = set(names_.keys()).intersection(expected_.keys())
            mapping.update({names_[name]: expected_[name] for name in exact})
            names -= {names_[name] for name in exact}
            expected -= {expected_[name] for name in exact}

    # Finally, try a more expensive similarity metric
    if names:
        import difflib

        for name in names:
            best_match = difflib.get_close_matches(name, expected, n=1)
            if best_match:
                mapping[name] = best_match[0]
                expected.remove(best_match[0])

    return mapping


def to_dict_of_lists[K, V](d: Iterable[Mapping[K, V]]) -> dict[K, list[V]]:
    """
    Map a list of dictionaries to a dictionary of lists.
    """
    result: dict[K, list[V]] = defaultdict(list)
    for item in d:
        for key, value in item.items():
            result[key].append(value)
    return result


def from_dict_of_lists[K, V](d: Mapping[K, Iterable[V]]) -> list[dict[K, V]]:
    """
    Map a dictionary of lists to a list of dictionaries.
    """
    keys = d.keys()
    values = zip(*d.values())
    return [dict(zip(keys, v)) for v in values]
