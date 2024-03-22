from __future__ import annotations

import dataclasses
import datetime
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from itertools import chain
from pathlib import PosixPath
from re import Pattern
from types import GeneratorType
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID

from logfire._utils import JsonValue, safe_repr

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase, DeclarativeMeta
else:
    try:
        from sqlalchemy.orm import DeclarativeBase, DeclarativeMeta
    except ImportError:  # pragma: no cover
        DeclarativeBase = type('DeclarativeBase', (), {})
        DeclarativeMeta = type('DeclarativeMeta', (), {})

try:
    import pydantic
except ModuleNotFoundError:  # pragma: no cover
    # pydantic is not installed, possible since it's not a dependency
    # don't add the types to the lookup logic
    pydantic = None

try:
    import pandas
except ModuleNotFoundError:  # pragma: no cover
    pandas = None

try:
    import numpy
except ModuleNotFoundError:  # pragma: no cover
    numpy = None

try:
    import attrs
except ModuleNotFoundError:  # pragma: no cover
    attrs = None

try:
    import sqlalchemy
    from sqlalchemy import inspect as sa_inspect
except ModuleNotFoundError:  # pragma: no cover
    sqlalchemy = None
    sa_inspect = None

__all__ = ('logfire_json_dumps',)

NUMPY_DIMENSION_MAX_SIZE = 10
"""The maximum size of a dimension of a numpy array."""


def _bytes_encoder(o: bytes) -> str:
    """Encode bytes using repr() to get a string representation of the bytes object.

    We remove the leading 'b' and the quotes around the string representation.

    Examples:
        >>> print(b'hello')
        b'hello'
        >>> print(_bytes_encoder(b'hello'))
        hello
    """
    return repr(o)[2:-1]


def _bytearray_encoder(o: bytearray) -> str:
    return _bytes_encoder(bytes(o))


def _set_encoder(o: set[Any]) -> JsonValue:
    try:
        return to_json_value(sorted(o))
    except TypeError:
        return to_json_value(list(o))


def _to_isoformat(o: Any) -> str:
    return o.isoformat()


def _pandas_data_frame_encoder(o: Any) -> JsonValue:
    """Encode pandas data frame by extracting important information.

    It summarizes rows and columns if they are more than limit.
    e.g. The data part of a data frame like:
    [
        [1, 2, 3, 4, 5],
        [2, 3, 6, 8, 10],
        [3, 6, 9, 12, 15],
        [4, 8, 12, 16, 20],
        [5, 10, 15, 20, 25],
    ]
    will be summarized to:
    [
        [1, 2, 4, 5],
        [2, 3, 8, 10],
        [4, 8, 16, 20],
        [5, 10, 20, 25],
    ]
    """
    import pandas

    max_rows = pandas.get_option('display.max_rows')
    max_columns = pandas.get_option('display.max_columns')

    col_middle = max_columns // 2
    column_count = len(o.columns)

    rows: list[Any] = []
    row_count = len(o)

    if row_count > max_rows:
        row_middle = max_rows // 2
        df_rows = chain(o.head(row_middle).iterrows(), o.tail(row_middle).iterrows())
    else:
        df_rows = o.iterrows()

    for _, row in df_rows:
        if column_count > max_columns:
            rows.append(list(row[:col_middle]) + list(row[-col_middle:]))
        else:
            rows.append(list(row))

    return to_json_value(rows)


def _numpy_array_encoder(o: Any) -> JsonValue:
    """Encode numpy array by extracting important information.

    It summarizes rows and columns if they are more than limit.
    e.g. The data part of a data frame like:
    [
        [1, 2, 3, 4, 5],
        [2, 3, 6, 8, 10],
        [3, 6, 9, 12, 15],
        [4, 8, 12, 16, 20],
        [5, 10, 15, 20, 25],
    ]
    will be summarized to:
    [
        [1, 2, 4, 5],
        [2, 3, 8, 10],
        [4, 8, 16, 20],
        [5, 10, 20, 25],
    ]
    """
    # If we reach here, numpy is installed.
    assert numpy and isinstance(o, numpy.ndarray)
    shape = o.shape
    dimensions = o.ndim

    if isinstance(o, numpy.matrix):
        o = o.A  # type: ignore[reportUnknownMemberType]

    for dimension in range(dimensions):
        # In case of multiple dimensions, we limit the dimension size by the NUMPY_DIMENSION_MAX_SIZE.
        half = min(shape[dimension], NUMPY_DIMENSION_MAX_SIZE) // 2
        # Slicing and concatenating arrays along the specified axis
        slices = [slice(None)] * dimensions
        slices[dimension] = slice(0, half)
        front = o[tuple(slices)]  # type: ignore[reportUnknownVariableType]

        slices[dimension] = slice(-half, None)
        end = o[tuple(slices)]  # type: ignore[reportUnknownVariableType]
        o = numpy.concatenate((front, end), axis=dimension)  # type: ignore[reportUnknownVariableType]

    return to_json_value(o.tolist())


def _pydantic_model_encoder(o: Any) -> JsonValue:
    assert pydantic and isinstance(o, pydantic.BaseModel)
    return to_json_value(o.model_dump())


def _get_sqlalchemy_data(o: Any) -> JsonValue:
    if sa_inspect is not None:  # pragma: no branch
        state = sa_inspect(o)
        deferred = state.unloaded
    else:  # pragma: no cover
        deferred = set()  # type: ignore

    return to_json_value(
        {field: getattr(o, field) if field not in deferred else '<deferred>' for field in o.__mapper__.attrs.keys()}
    )


EncoderFunction = Callable[[Any], JsonValue]


@lru_cache(maxsize=None)
def encoder_by_type() -> dict[type[Any], EncoderFunction]:
    lookup: dict[type[Any], EncoderFunction] = {
        set: _set_encoder,
        frozenset: _set_encoder,
        bytes: _bytes_encoder,
        bytearray: _bytearray_encoder,
        datetime.date: _to_isoformat,
        datetime.datetime: _to_isoformat,
        datetime.time: _to_isoformat,
        datetime.timedelta: lambda o: str(o.total_seconds()),
        Decimal: str,
        Enum: lambda o: to_json_value(o.value),
        GeneratorType: repr,
        IPv4Address: str,
        IPv4Interface: str,
        IPv4Network: str,
        IPv6Address: str,
        IPv6Interface: str,
        IPv6Network: str,
        PosixPath: str,
        Pattern: lambda o: to_json_value(o.pattern),
        UUID: str,
        Exception: str,
    }
    if pydantic:  # pragma: no cover
        lookup.update(
            {
                pydantic.AnyUrl: str,
                pydantic.NameEmail: str,
                pydantic.SecretBytes: str,
                pydantic.SecretStr: str,
                pydantic.BaseModel: _pydantic_model_encoder,
            }
        )

    if pandas:  # pragma: no cover
        lookup.update({pandas.DataFrame: _pandas_data_frame_encoder})
    if numpy:  # pragma: no cover
        lookup.update({numpy.ndarray: _numpy_array_encoder})

    return lookup


def to_json_value(o: Any) -> JsonValue:
    try:
        if isinstance(o, (int, float, str, bool, type(None))):
            return o
        elif isinstance(o, Mapping):
            return {key if isinstance(key, str) else safe_repr(key): to_json_value(value) for key, value in o.items()}  # type: ignore
        elif dataclasses.is_dataclass(o):
            return {f.name: to_json_value(getattr(o, f.name)) for f in dataclasses.fields(o)}
        elif attrs is not None and attrs.has(o.__class__):
            return {f.name: to_json_value(getattr(o, f.name)) for f in attrs.fields(o.__class__)}
        elif is_sqlalchemy(o):
            return _get_sqlalchemy_data(o)

        # Check the class type and its superclasses for a matching encoder
        for base in o.__class__.__mro__[:-1]:
            try:
                encoder = encoder_by_type()[base]
            except KeyError:
                pass
            else:
                return encoder(o)

        if isinstance(o, Sequence):
            return [to_json_value(item) for item in o]  # type: ignore
    except Exception:  # pragma: no cover
        pass

    # In case we don't know how to encode, use `repr()`.
    return safe_repr(o)


def logfire_json_dumps(obj: Any) -> str:
    return json.dumps(to_json_value(obj), separators=(',', ':'))


def is_sqlalchemy(obj: Any) -> bool:
    if sqlalchemy is None:  # pragma: no cover
        return False
    if isinstance(obj, DeclarativeBase):
        return True
    return isinstance(obj.__class__, DeclarativeMeta)
