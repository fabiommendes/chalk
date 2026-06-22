from typing import Any, Callable, Iterable, Mapping


def unique[T](data: Iterable[T], /) -> list[T]:
    """
    Return a list of unique items from the given iterable, preserving the order.
    """

    data = list(data)
    seen: Any = set()
    result = []

    visit = seen.add

    for item in data:
        if item not in seen:
            try:
                visit(item)
            except TypeError:  # non-hashable item
                seen = list(seen)
                visit = seen.append
                visit(item)

            result.append(item)

    return result


def flatten[T](data: Iterable[Iterable[T]], /) -> list[T]:
    """
    Flatten a nested iterable into a single list.
    """
    return [item for sublist in data for item in sublist]


def find_path(
    pred: Callable[[Any], bool], data: Any, /, path: str = ""
) -> tuple[str, Any] | None:
    """
    Return the path of the first item that obey the given predicate in a nested
    data structure (usually formed by dicts and lists).
    """

    if isinstance(data, Mapping):
        for key, value in data.items():
            if pred(value):
                return f"{path}.{key}", value
            else:
                child = find_path(pred, value, f"{path}.{key}")
                if child is not None:
                    return child

    elif isinstance(data, Iterable) and not isinstance(data, (str, bytes)):
        for index, item in enumerate(data):
            if pred(item):
                return f"{path}.{index}", item

            child = find_path(pred, item, f"{path}.{index}")
            if child is not None:
                return child

    return None


def get_path(data: Any, path: str, /) -> Any:
    """
    Return the item in a nested data structure (usually formed by dicts and lists)
    at the given path.
    """

    if path == "/":
        return data

    parts = path.strip("/").split("/")
    current = data

    for part in parts:
        if isinstance(current, Mapping):
            current = current[part]
        elif isinstance(current, Iterable) and not isinstance(current, (str, bytes)):
            index = int(part)
            try:
                current = current[index]  # type: ignore
            except IndexError:
                for i, x in enumerate(current):
                    if i == index:
                        current = x
                        break
                else:
                    raise IndexError(f"Index {index} out of range for path: {path}")
        else:
            raise ValueError(f"Invalid path: {path}")

    return current
