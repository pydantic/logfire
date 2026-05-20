from functools import cache, lru_cache
from typing import Any

from _typeshed import Incomplete

from .artifacts import Artifact as Artifact
from .utils import JsonValue as JsonValue, safe_repr as safe_repr

NUMPY_DIMENSION_MAX_SIZE: int
EncoderFunction: Incomplete

@cache
def encoder_by_type() -> dict[type[Any], EncoderFunction]: ...
def to_json_value(o: Any, seen: set[int]) -> JsonValue: ...
def logfire_json_dumps(obj: Any) -> str: ...
def is_sqlalchemy(obj: Any) -> bool: ...
@lru_cache
def is_attrs(cls) -> bool: ...
