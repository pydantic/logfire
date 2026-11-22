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
def numpy_scalar_to_python(o: Any) -> Any:
    """Convert a NumPy bool, integer or floating scalar to the equivalent Python value, and return anything else as is.

    Without this, a value like `numpy.int64(42)` (e.g. from `df['col'].sum()`) would be recorded as its repr.
    """
def to_json_value(o: Any, seen: set[int]) -> JsonValue: ...
def logfire_json_dumps(obj: Any) -> str: ...
def is_sqlalchemy(obj: Any) -> bool: ...
@lru_cache
def is_attrs(cls) -> bool: ...
