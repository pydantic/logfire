from .utils import JsonValue as JsonValue, safe_repr as safe_repr
from _typeshed import Incomplete
from functools import cache, lru_cache
from typing import Any

NUMPY_DIMENSION_MAX_SIZE: int

def pandas_display_slices(count: int, limit: int | None) -> tuple[slice, ...]:
    """Return the first and last positions selected by a pandas display limit."""

EncoderFunction: Incomplete

@cache
def encoder_by_type() -> dict[type[Any], EncoderFunction]: ...
def to_json_value(o: Any, seen: set[int]) -> JsonValue: ...
def logfire_json_dumps(obj: Any) -> str: ...
def is_sqlalchemy(obj: Any) -> bool: ...
@lru_cache
def is_attrs(cls) -> bool: ...
