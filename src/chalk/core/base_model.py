from typing import Any, overload

from pydantic import BaseModel


class BaseChalkModel(BaseModel):
    """
    Base model for Chalk data structures.
    """

    __slots__ = ("_cache",)

    def _memoize(self, key: str, value: object) -> None:
        if not hasattr(self, "_cache"):
            object.__setattr__(self, "_cache", cache := {})
        else:
            cache = self._cache
        cache[key] = value

    @overload
    def _memoized[T: type](self, key: str, type: T) -> T | None: ...

    @overload
    def _memoized(self, key: str) -> object: ...

    def _memoized(self, key: str, type: type = object) -> Any:
        if not hasattr(self, "_cache"):
            return None
        value = self._cache.get(key)
        if value is None:
            return value
        elif isinstance(value, type):
            return value

        msg = f"Invalid memoized value for {key}: expected {type}, got {type(value)}"
        raise TypeError(msg)
