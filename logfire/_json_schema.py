"""The JSON Schema generator for Logfire.

There are custom keywords in the generated JSON Schema. They are prefixed with `x-` to avoid
conflicts with the official keywords. The custom keywords are:

- `x-python-datatype`: The Python data type of the value. It is used to generate the Python type hints.
- `x-columns`: The column names of the data frame. It is used to generate the Python type.
- `x-indexes`: The index names of the data frame. It is used to generate the Python type.
- `x-shape`: The shape of the numpy array. It is used to generate the Python type.
- `x-dtype`: The data type of the numpy array. It is used to generate the Python type.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import re
import uuid
from collections import deque
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import PosixPath
from types import GeneratorType
from typing import Any, Callable, Mapping, Sequence, cast

from logfire._json_encoder import _is_sqlalchemy  # type: ignore[reportPrivateUsage]

try:
    import pydantic
except ModuleNotFoundError:  # pragma: no cover
    pydantic = None

try:
    import attrs
except ModuleNotFoundError:  # pragma: no cover
    attrs = None

try:
    import pandas
except ModuleNotFoundError:  # pragma: no cover
    pandas = None

try:
    import numpy
except ModuleNotFoundError:  # pragma: no cover
    numpy = None

try:
    import sqlalchemy
    from sqlalchemy import inspect as sa_inspect
except ModuleNotFoundError:  # pragma: no cover
    sqlalchemy = None
    sa_inspect = None

__all__ = 'create_json_schema', 'logfire_json_schema'


@lru_cache
def type_to_schema() -> dict[type[Any], dict[str, Any] | Callable[[Any], dict[str, Any]]]:
    return {
        bytes: _bytes_schema,
        bytearray: _bytearray_schema,
        Enum: _enum_schema,
        Decimal: {'type': 'string', 'format': 'decimal'},
        datetime.datetime: {'type': 'string', 'format': 'date-time'},
        datetime.date: {'type': 'string', 'format': 'date'},
        datetime.time: {'type': 'string', 'format': 'time'},
        datetime.timedelta: {'type': 'string', 'x-python-datatype': 'timedelta'},
        list: _array_schema,
        tuple: _array_schema,
        set: _array_schema,
        frozenset: _array_schema,
        deque: _array_schema,
        GeneratorType: _generator_schema,
        IPv4Address: {'type': 'string', 'format': 'ipv4'},
        IPv6Address: {'type': 'string', 'format': 'ipv6'},
        IPv4Interface: {'type': 'string', 'format': 'ipv4interface'},
        IPv6Interface: {'type': 'string', 'format': 'ipv6interface'},
        IPv4Network: {'type': 'string', 'format': 'ipv4network'},
        IPv6Network: {'type': 'string', 'format': 'ipv6network'},
        re.Pattern: {'type': 'string', 'format': 'regex'},
        uuid.UUID: {'type': 'string', 'format': 'uuid'},
        range: {'type': 'array', 'x-python-datatype': 'range'},
        PosixPath: {'type': 'string', 'format': 'path', 'x-python-datatype': 'PosixPath'},
        Exception: _exception_schema,
        **dict(
            {}
            if pydantic is None
            else {
                pydantic.AnyUrl: {'type': 'string', 'format': 'uri'},
                pydantic.NameEmail: {'type': 'string', 'x-python-datatype': 'NameEmail'},
                pydantic.SecretStr: {'type': 'string', 'x-python-datatype': 'SecretStr'},
                pydantic.SecretBytes: {'type': 'string', 'x-python-datatype': 'SecretBytes'},
                pydantic.BaseModel: _pydantic_model_schema,
            }
        ),
        **dict({} if pandas is None else {pandas.DataFrame: _pandas_schema}),
        **dict({} if numpy is None else {numpy.ndarray: _numpy_schema}),
    }


_type_to_schema = None


def create_json_schema(obj: Any) -> dict[str, Any]:
    """Create a JSON Schema from the given object.

    Args:
        obj: The object to create the JSON Schema from.

    Returns:
        The JSON Schema.
    """
    if dataclasses.is_dataclass(obj):
        return _dataclass_schema(obj)
    elif isinstance(obj, Mapping):
        return _mapping_schema(obj)
    elif attrs and attrs.has(obj):
        return _attrs_schema(obj)
    elif _is_sqlalchemy(obj):
        return _sqlalchemy_schema(obj)

    global _type_to_schema
    _type_to_schema = _type_to_schema or type_to_schema()
    for base in obj.__class__.__mro__[:-1]:
        try:
            schema = _type_to_schema[base]
        except KeyError:
            continue
        else:
            return schema(obj) if callable(schema) else schema

    if obj is None or isinstance(obj, (str, int, bool, float)):
        return {}
    elif isinstance(obj, Sequence) and not isinstance(obj, str):
        name = obj.__class__.__name__  # type: ignore[reportUnknownMemberType]
        return {'type': 'array', 'title': name, 'x-python-datatype': 'Sequence'}

    return {'type': 'object', 'title': obj.__class__.__name__, 'x-python-datatype': 'unknown'}


# NOTE: The code related attributes are merged with the logfire function attributes on
# `auto_install_tracing` and when using our stdlib logging handler. We need to remove them
# from the JSON Schema, as we only want to have the ones that the user passes in.
_CODE_KEYS = {'code.lineno', 'code.filepath', 'code.function', 'code.namespace'}


def logfire_json_schema(obj: dict[str, Any]) -> str | None:
    obj = {k: v for k, v in obj.items() if k not in _CODE_KEYS}

    json_schema = _mapping_schema(obj, is_top_level=True)
    if json_schema == {'type': 'object'}:
        return None

    if pydantic:
        import pydantic_core

        return pydantic_core.to_json(json_schema).decode()
    else:  # pragma: no cover
        return json.dumps(json_schema, separators=(',', ':'))


def _dataclass_schema(obj: Any) -> dict[str, str]:
    datatype = 'pydantic-dataclass' if hasattr(obj, '__pydantic_config__') else 'dataclass'
    schema = {'type': 'object', 'title': obj.__class__.__name__, 'x-python-datatype': datatype}

    properties: dict[str, dict[str, Any]] = {}
    for field in dataclasses.fields(obj):
        if field_schema := create_json_schema(getattr(obj, field.name)):
            properties[field.name] = field_schema
    if properties:
        schema['properties'] = properties
    return schema


def _bytes_schema(obj: bytes) -> dict[str, str]:
    schema = {'type': 'string', 'x-python-datatype': 'bytes'}
    if obj.__class__.__name__ != 'bytes':
        schema['title'] = obj.__class__.__name__
    return schema


def _bytearray_schema(obj: bytearray) -> dict[str, str]:
    schema = {'type': 'string', 'x-python-datatype': 'bytearray'}
    if obj.__class__.__name__ != 'bytearray':
        schema['title'] = obj.__class__.__name__
    return schema


# NOTE: We don't handle enums where members are not basic types (str, int, bool, float) very well.
# The "type" will always be "object".
def _enum_schema(obj: Enum) -> dict[str, str | list[Any]]:
    enum_values = [e.value for e in obj.__class__]
    enum_types = set(type(value).__name__ for value in enum_values)
    if all(t in {'str', 'int', 'bool', 'float'} for t in enum_types):
        type_ = {'str': 'string', 'int': 'integer', 'bool': 'boolean', 'float': 'number'}[enum_types.pop()]
    else:
        type_ = 'object'

    return {
        'type': type_,
        'title': obj.__class__.__name__,
        'x-python-datatype': 'enum',
        'enum': enum_values,
    }


def _mapping_schema(obj: Any, is_top_level: bool = False) -> dict[str, str]:
    obj = cast(Mapping[Any, Any], obj)
    schema: dict[str, Any] = {'type': 'object'}
    properties: dict[str, dict[str, Any]] = {}
    for k, v in obj.items():
        value = create_json_schema(v)
        if value != {} or is_top_level:
            properties[k] = value
    if properties:
        schema['properties'] = properties
    if obj.__class__.__name__ != 'dict':
        schema['x-python-datatype'] = 'Mapping'
        schema['title'] = obj.__class__.__name__
    return schema


def _array_schema(obj: list[Any] | tuple[Any, ...] | deque[Any] | set[Any] | frozenset[Any]) -> dict[str, str]:
    schema: dict[str, Any] = {'type': 'array', 'x-python-datatype': obj.__class__.__name__}
    if isinstance(obj, (set, frozenset)):
        try:
            obj = sorted(obj)
        except TypeError:
            return schema
    prefix_items: list[Any] = []

    if len(obj) == 0:
        return schema

    previous_schema: dict[str, Any] | None = None
    use_items_key = True
    found_non_empty_schema = False
    for item in obj:
        item_schema = create_json_schema(item)
        prefix_items.append(item_schema)

        if previous_schema is not None and item_schema != previous_schema:
            use_items_key = False
        if item_schema != {}:
            found_non_empty_schema = True

        previous_schema = item_schema

    if found_non_empty_schema:
        if use_items_key:
            schema['items'] = previous_schema
        else:
            schema['prefixItems'] = prefix_items
    return schema


def _generator_schema(obj: GeneratorType[Any, Any, Any]) -> dict[str, str]:
    return {'type': 'array', 'x-python-datatype': 'generator', 'title': obj.__class__.__name__}


def _exception_schema(obj: Exception) -> dict[str, str]:
    return {'type': 'object', 'title': obj.__class__.__name__, 'x-python-datatype': 'Exception'}


def _pydantic_model_schema(obj: Any) -> dict[str, Any]:
    import pydantic

    assert isinstance(obj, pydantic.BaseModel)
    schema: dict[str, str | dict[str, Any]] = {
        'type': 'object',
        'title': obj.__class__.__name__,
        'x-python-datatype': 'PydanticModel',
    }
    properties: dict[str, dict[str, Any]] = {}
    for key in obj.model_fields.keys():
        if field_schema := create_json_schema(getattr(obj, key)):
            properties[key] = field_schema
    extras = obj.model_extra or {}
    for key in extras.keys():
        if field_schema := create_json_schema(getattr(obj, key)):
            properties[key] = field_schema
    if properties:
        schema['properties'] = properties
    return schema


def _pandas_schema(obj: Any) -> dict[str, Any]:
    import pandas

    assert isinstance(obj, pandas.DataFrame)

    row_count, column_count = obj.shape

    max_columns = pandas.get_option('display.max_columns')
    col_middle = min(max_columns, column_count) // 2
    columns = list(obj.columns[:col_middle]) + list(obj.columns[-col_middle:])  # type: ignore

    max_rows = pandas.get_option('display.max_rows')
    rows = min(max_rows, row_count) // 2
    indexes = list(obj.index[:rows]) + list(obj.index[-rows:])  # type: ignore

    return {'type': 'array', 'x-python-datatype': 'DataFrame', 'x-columns': columns, 'x-indexes': indexes}


def _numpy_schema(obj: Any) -> dict[str, Any]:
    import numpy

    assert isinstance(obj, numpy.ndarray)

    return {
        'type': 'array',
        'x-python-datatype': 'ndarray',
        'x-shape': obj.shape,
        'x-dtype': str(obj.dtype),  # type: ignore
    }


def _attrs_schema(obj: Any) -> dict[str, str]:
    import attrs

    obj = cast(attrs.AttrsInstance, obj)
    schema = {
        'type': 'object',
        'title': obj.__class__.__name__,
        'x-python-datatype': 'attrs',
    }
    properties: dict[str, dict[str, Any]] = {}
    for key in obj.__attrs_attrs__:
        if field_schema := create_json_schema(getattr(obj, key.name)):
            properties[key.name] = field_schema
    if properties:
        schema['properties'] = properties
    return schema


def _sqlalchemy_schema(obj: Any) -> dict[str, str]:
    assert sqlalchemy and sa_inspect

    schema = {
        'type': 'object',
        'title': obj.__class__.__name__,
        'x-python-datatype': 'sqlalchemy',
    }
    properties: dict[str, dict[str, Any]] = {}
    for key in sa_inspect(obj).attrs.keys():
        if field_schema := create_json_schema(getattr(obj, key)):
            properties[key] = field_schema
    if properties:
        schema['properties'] = properties
    return schema
