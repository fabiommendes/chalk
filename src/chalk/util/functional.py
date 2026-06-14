from functools import cmp_to_key
from typing import Callable, Mapping, Protocol


class DispatchFn[T, R, **P](Protocol):
    def __call__(self, value: T, /, *args: P.args, **kwargs: P.kwargs) -> R: ...


def type_mapper[T, R, **P](
    mapping: Mapping[type, DispatchFn[T, R, P]],
    default: Callable[..., R] | None = None,
) -> DispatchFn[T, R, P]:
    """
    Create a mapping function that maps values based on their type using the provided mapping.
    """

    def sort_resolution_order() -> None:
        resolution_order.sort(
            key=cmp_to_key(lambda a, b: issubclass(a, b) - issubclass(b, a))
        )

    def map_value(value: T, /, *args: P.args, **kwargs: P.kwargs) -> R:
        value_type = type(value)
        try:
            return map_cache[value_type](value, *args, **kwargs)
        except KeyError:
            for t in resolution_order:
                if issubclass(value_type, t):
                    map_cache[t] = impl = mapping[t]
                    sort_resolution_order()

                    return impl(value, *args, **kwargs)

        if default is not None:
            return default(value)
        raise TypeError(f"{value_type} is not supported.")

    map_cache = {**mapping}
    resolution_order = list(mapping.keys())
    sort_resolution_order()

    return map_value
