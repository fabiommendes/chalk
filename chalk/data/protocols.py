from typing import Protocol, Self


class Serializable(Protocol):
    def serialize(self, /) -> str: ...

    @classmethod
    def deserialize(cls, value: str, /) -> Self: ...


class JSONSerializable(Protocol):
    def to_json(self, /) -> str: ...

    @classmethod
    def from_json(cls, value: str, /) -> Self: ...


class HasId[T = str](Protocol):
    @property
    def id(self, /) -> T: ...


#
# Utility functions
#
def get_id(item: HasId | str) -> str:
    """
    Get the ID of an item that has an 'id' attribute or is a string.
    """
    if isinstance(item, str):
        return item
    return item.id
