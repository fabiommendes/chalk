from collections.abc import Callable, Mapping
from functools import cmp_to_key
from operator import attrgetter
from typing import Any, Protocol, Self, overload

from typing_extensions import TypeForm


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
        resolution_order.sort(key=cmp_to_key(lambda a, b: issubclass(a, b) - issubclass(b, a)))

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


class Descriptor(Protocol):
    def __get__(self, instance: object | None, owner: type | None = None) -> object: ...
    def __set__(self, instance: object, value: object) -> None: ...
    def __delete__(self, instance: object) -> None: ...


class GetDescriptor[T, R](Protocol):
    @overload
    def __get__(self, instance: T, owner: type[T] | None = None) -> R: ...

    @overload
    def __get__(self, instance: None, owner: type[T]) -> Self: ...


class GetSetDescriptor[T, R](GetDescriptor[T, R], Protocol):
    def __set__(self, instance: T, value: R) -> None: ...


def rw_delegate[T](attr: str, type: TypeForm[T]) -> GetSetDescriptor[Any, T]:
    """
    Create a property that delegates access to another (possibly nested)
    attribute of the object.
    """

    root, leaf = attr.rsplit(".", 1) if "." in attr else (attr, None)

    getter: Callable[[str], T] = attrgetter(attr)
    if leaf is None:

        def setter(self, value: T) -> None:
            setattr(self, attr, value)

    else:
        root_getter = attrgetter(root)

        def setter(self, value: T) -> None:
            setattr(root_getter(self), leaf, value)

    return property(getter, setter)  # type: ignore


def ro_delegate[T](attr: str, type: TypeForm[T], /) -> GetDescriptor[Any, T]:
    """
    Create a read-only property that delegates access to another (possibly nested)
    attribute of the object.
    """

    getter: Callable[[str], T] = attrgetter(attr)
    return property(getter)  # type: ignore


def thunk[T](func: Callable[[], T], /) -> Callable[[], T]:
    """
    Create a thunk that caches the result of a function call.
    """

    is_empty: Any = object()
    cache: T = is_empty

    def thunk() -> T:
        nonlocal cache
        if cache is is_empty:
            cache = func()
        return cache

    return thunk
