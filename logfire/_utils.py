from __future__ import annotations

import json
import sys
from pathlib import Path
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


def truncate_string(s: str, *, max_length: int, middle: str = '...') -> str:
    """Return a string at most max_length characters long, with `middle` in the middle if truncated."""
    if len(s) <= max_length:
        return s
    remaining_length = max_length - len(middle)
    half = remaining_length // 2
    return s[:half] + middle + s[-half:]


def read_toml_file(path: Path) -> dict[str, Any]:
    """Read a TOML file and return the parsed data.

    It wraps the `tomllib.load` function from Python 3.11 or the `tomli.load` function from older versions.
    """
    if sys.version_info >= (3, 11):
        from tomllib import load as load_toml
    else:
        from tomli import load as load_toml

    with path.open('rb') as f:
        data = load_toml(f)

    return data
