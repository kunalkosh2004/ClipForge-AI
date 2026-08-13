from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T")


@dataclass
class PageRequest:
    limit: int = 20
    offset: int = 0

    @classmethod
    def from_query(cls, limit: int = 20, offset: int = 0) -> "PageRequest":
        return cls(limit=min(limit, 100), offset=max(offset, 0))


@dataclass
class PageResult[T]:
    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return (self.offset + self.limit) < self.total


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool
