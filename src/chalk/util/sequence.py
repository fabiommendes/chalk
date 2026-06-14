from typing import Any, Iterable


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
