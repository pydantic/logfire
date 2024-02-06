from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Tuple, TypeVar, Union

T = TypeVar('T')

JsonValue = Union[int, float, str, bool, None, List['JsonValue'], Tuple['JsonValue', ...], 'JsonDict']
JsonDict = Dict[str, JsonValue]

try:
    import pydantic_core
except Exception:  # pragma: no cover

    def dump_json(obj: JsonValue) -> str:
        return json.dumps(obj, separators=(',', ':'))
else:

    def dump_json(obj: JsonValue) -> str:
        return pydantic_core.to_json(obj).decode()


def uniquify_sequence(seq: Sequence[T]) -> list[T]:
    """Remove duplicates from a sequence preserving order."""
    seen: set[T] = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]


def safe_repr(obj: Any) -> str:
    """Return some kind of non-empty string representation of an object, catching exceptions."""
    try:
        result = repr(obj)
    except Exception:
        result = ''

    # If repr() returns an empty string, don't use that.
    if result:
        return result

    try:
        return f'<{type(obj).__name__} object>'
    except Exception:
        return '<unknown (repr failed)>'
