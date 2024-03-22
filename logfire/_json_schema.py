"""The JSON Schema generator for Logfire.

There are custom keywords in the generated JSON Schema. They are prefixed with `x-` to avoid
conflicts with the official keywords. The custom keywords are:

- `x-python-datatype`: The Python data type of the value. It is used to generate the Python type hints.
- `x-columns`: The column names of the data frame. It is used to generate the Python type.
- `x-indices`: The index names of the data frame. It is used to generate the Python type.
- `x-column-count`: The number of columns in the data frame. It is used to generate the Python type.
- `x-row-count`: The number of rows in the data frame. It is used to generate the Python type.
- `x-shape`: The shape of the numpy array. It is used to generate the Python type.
- `x-dtype`: The data type of the numpy array. It is used to generate the Python type.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
import uuid
from collections import deque
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import PosixPath
from types import GeneratorType
from typing import Any, Callable, Iterable, Mapping, NewType, Sequence, cast

from logfire._json_encoder import is_sqlalchemy, to_json_value
from logfire._stack_info import STACK_INFO_KEYS
from logfire._utils import JsonDict, dump_json, safe_repr

try:
    import pydantic
    import pydantic_core
except ModuleNotFoundError:  # pragma: no cover
    pydantic = None
    pydantic_core = None

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

__all__ = 'create_json_schema', 'attributes_json_schema_properties', 'attributes_json_schema'


@lru_cache
def type_to_schema() -> dict[type[Any], JsonDict | Callable[[Any], JsonDict]]:
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
            if pydantic is None or pydantic_core is None
            else {
                pydantic_core.Url: {'type': 'string', 'x-python-datatype': 'Url'},
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


def create_json_schema(obj: Any) -> JsonDict:
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
    elif is_sqlalchemy(obj):
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

    return {'type': 'object', 'x-python-datatype': 'unknown'}


JsonSchemaProperties = NewType('JsonSchemaProperties', JsonDict)


# The value of the span attribute with key ATTRIBUTES_JSON_SCHEMA_KEY,
# representing the JSON schema of the user-defined attributes.
def attributes_json_schema(properties: JsonSchemaProperties) -> str:
    return dump_json({'type': 'object', 'properties': properties})


# This becomes the value of `properties` above.
def attributes_json_schema_properties(attributes: dict[str, Any]) -> JsonSchemaProperties:
    return JsonSchemaProperties(
        # NOTE: The code related attributes are merged with the logfire function attributes on
        # `install_auto_tracing` and when using our stdlib logging handler. We need to remove them
        # from the JSON Schema, as we only want to have the ones that the user passes in.
        {key: create_json_schema(value) for key, value in attributes.items() if key not in STACK_INFO_KEYS}
    )


def _dataclass_schema(obj: Any) -> JsonDict:
    # NOTE: The `x-python-datatype` is "dataclass" for both standard dataclasses and Pydantic dataclasses.
    # We don't need to distinguish between them on the frontend, or to reconstruct the type on the JSON formatter.
    return _custom_object_schema(obj, 'dataclass', (field.name for field in dataclasses.fields(obj)))


def _bytes_schema(obj: bytes) -> JsonDict:
    schema: JsonDict = {'type': 'string', 'x-python-datatype': 'bytes'}
    if obj.__class__.__name__ != 'bytes':
        schema['title'] = obj.__class__.__name__
    return schema


def _bytearray_schema(obj: bytearray) -> JsonDict:
    schema: JsonDict = {'type': 'string', 'x-python-datatype': 'bytearray'}
    # TODO(Marcelo): We should add a test for the following branch.
    if obj.__class__.__name__ != 'bytearray':  # pragma: no cover
        schema['title'] = obj.__class__.__name__
    return schema


# NOTE: We don't handle enums where members are not basic types (str, int, bool, float) very well.
# The "type" will always be "object".
def _enum_schema(obj: Enum) -> JsonDict:
    enum_values = [e.value for e in obj.__class__]
    enum_types = set(type(value).__name__ for value in enum_values)
    if all(t in {'str', 'int', 'bool', 'float'} for t in enum_types):
        type_ = {'str': 'string', 'int': 'integer', 'bool': 'boolean', 'float': 'number'}[enum_types.pop()]
    else:
        type_ = 'object'

    return {
        'type': type_,
        'title': obj.__class__.__name__,
        'x-python-datatype': 'Enum',
        'enum': to_json_value(enum_values),
    }


# Schemas for values that are already JSON serializable, i.e. that don't need to be included
# (except at the top level) because the frontend can just render them as plain JSON.
PLAIN_SCHEMAS: tuple[JsonDict, ...] = ({}, {'type': 'object'}, {'type': 'array'})


def _mapping_schema(obj: Any) -> JsonDict:
    obj = cast(Mapping[Any, Any], obj)
    schema: JsonDict = {
        'type': 'object',
        **_properties({(k if isinstance(k, str) else safe_repr(k)): v for k, v in obj.items()}),
    }
    if obj.__class__.__name__ != 'dict':
        schema['x-python-datatype'] = 'Mapping'
        schema['title'] = obj.__class__.__name__
    return schema


def _array_schema(obj: list[Any] | tuple[Any, ...] | deque[Any] | set[Any] | frozenset[Any]) -> JsonDict:
    schema: dict[str, Any] = {'type': 'array'}
    if type(obj) != list:  # noqa: E721
        schema['x-python-datatype'] = obj.__class__.__name__

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
        if item_schema not in PLAIN_SCHEMAS:
            found_non_empty_schema = True

        previous_schema = item_schema

    if found_non_empty_schema:
        if use_items_key:
            schema['items'] = previous_schema
        else:
            schema['prefixItems'] = prefix_items
    return schema


def _generator_schema(obj: GeneratorType[Any, Any, Any]) -> JsonDict:
    return {'type': 'array', 'x-python-datatype': 'generator', 'title': obj.__class__.__name__}


def _exception_schema(obj: Exception) -> JsonDict:
    return {'type': 'object', 'title': obj.__class__.__name__, 'x-python-datatype': 'Exception'}


def _pydantic_model_schema(obj: Any) -> JsonDict:
    assert pydantic and isinstance(obj, pydantic.BaseModel)
    return _custom_object_schema(obj, 'PydanticModel', [*obj.model_fields, *(obj.model_extra or {})])


def _pandas_schema(obj: Any) -> JsonDict:
    assert pandas and isinstance(obj, pandas.DataFrame)

    row_count, column_count = obj.shape

    max_columns = pandas.get_option('display.max_columns')
    col_middle = min(max_columns, column_count) // 2
    columns = list(obj.columns[:col_middle]) + list(obj.columns[-col_middle:])  # type: ignore

    max_rows = pandas.get_option('display.max_rows')
    row_middle = min(max_rows, row_count) // 2
    indices = list(obj.index[:row_middle]) + list(obj.index[-row_middle:])  # type: ignore

    return {
        'type': 'array',
        'x-python-datatype': 'DataFrame',
        'x-columns': columns,
        'x-column-count': column_count,
        'x-indices': indices,
        'x-row-count': row_count,
    }


def _numpy_schema(obj: Any) -> JsonDict:
    import numpy

    assert isinstance(obj, numpy.ndarray)

    return {
        'type': 'array',
        'x-python-datatype': 'ndarray',
        'x-shape': obj.shape,
        'x-dtype': str(obj.dtype),  # type: ignore
    }


def _attrs_schema(obj: Any) -> JsonDict:
    import attrs

    obj = cast(attrs.AttrsInstance, obj)
    return _custom_object_schema(obj, 'attrs', (key.name for key in obj.__attrs_attrs__))


def _sqlalchemy_schema(obj: Any) -> JsonDict:
    assert sqlalchemy and sa_inspect
    return _custom_object_schema(obj, 'sqlalchemy', sa_inspect(obj).attrs.keys())


def _properties(properties: dict[str, Any]) -> JsonDict:
    schema_properties: JsonDict = {}
    for key, value in properties.items():
        if (value_schema := create_json_schema(value)) not in PLAIN_SCHEMAS:
            schema_properties[key] = value_schema

    if schema_properties:
        return {'properties': schema_properties}
    else:
        return {}


def _custom_object_schema(obj: Any, datatype_name: str, keys: Iterable[str]) -> JsonDict:
    return {
        'type': 'object',
        'title': obj.__class__.__name__,
        'x-python-datatype': datatype_name,
        **_properties({key: getattr(obj, key) for key in keys}),
    }
