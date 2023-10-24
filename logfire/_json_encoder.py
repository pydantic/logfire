from __future__ import annotations

import base64
import dataclasses
import datetime
import json
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from enum import Enum
from functools import cached_property
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import PosixPath
from re import Pattern
from types import GeneratorType
from typing import Any, Literal, Protocol
from uuid import UUID

try:
    import pydantic
except ImportError:
    # pydantic is not installed, possible since it's not a dependency
    # don't add the types to the lookup logic
    pydantic = None

__all__ = 'LogfireEncoder', 'logfire_json_dumps', 'json_dumps_traceback', 'DataType'


class EncoderFunction(Protocol):
    def __call__(self, obj: Any, subclass: bool = False, /) -> dict[str, Any]:
        ...


DataType = Literal[
    # scalar types
    'Decimal',
    'UUID',
    'Enum',
    # bytes
    'bytes-base64',
    'bytes-utf8',
    # temporal types
    'date',
    'datetime',
    'time',
    'timedelta',
    # ipaddress types
    'IPv4Address',
    'IPv4Interface',
    'IPv4Network',
    'IPv6Address',
    'IPv6Interface',
    'IPv6Network',
    'PosixPath',
    'Pattern',
    # iterable types
    'set',
    'frozenset',
    'tuple',
    'deque',
    'generator',
    'Mapping',
    'Sequence',
    'dataclass',
    # exceptions
    'Exception',
    # pydantic types
    'BaseModel',
    'Url',
    'NameEmail',
    'SecretBytes',
    'SecretStr',
    # any other type
    'unknown',
]


class LogfireEncoder(json.JSONEncoder):
    @staticmethod
    def _create_result_dict(data_type: DataType, data: Any, **kwargs: Any) -> dict[str, Any]:
        return {'$__datatype__': data_type, 'data': data, **kwargs}

    @staticmethod
    def _bytes_encoder(o: Any, subclass: bool = False) -> dict[str, Any]:
        kwargs = {'cls': o.__class__.__name__} if subclass else {}
        try:
            bytes_utf8 = o.decode()
        except UnicodeDecodeError:
            base64_bytes = base64.b64encode(o).decode()
            return LogfireEncoder._create_result_dict(data_type='bytes-base64', data=base64_bytes, **kwargs)
        else:
            return LogfireEncoder._create_result_dict(data_type='bytes-utf8', data=bytes_utf8, **kwargs)

    @staticmethod
    def _cls_encoder(
        data_type: DataType, encoder: Callable[[Any], Any], o: Any, _subclass: bool = False
    ) -> dict[str, Any]:
        return LogfireEncoder._create_result_dict(data_type=data_type, data=encoder(o), cls=o.__class__.__name__)

    @staticmethod
    def _uuid_encoder(o: Any, _subclass: bool = False) -> dict[str, Any]:
        return LogfireEncoder._create_result_dict(data_type='UUID', data=str(o), version=o.version)

    @staticmethod
    def _build_cls_encoder(data_type: DataType, encoder: Callable[[Any], Any]) -> EncoderFunction:
        def cls_encoder(o: Any, _subclass: bool = False) -> dict[str, Any]:
            return LogfireEncoder._create_result_dict(data_type=data_type, data=encoder(o), cls=o.__class__.__name__)

        return cls_encoder

    @staticmethod
    def _build_default_encoder(data_type: DataType, encoder: Callable[[Any], Any]) -> EncoderFunction:
        def type_encoder(o: Any, subclass: bool = False) -> dict[str, Any]:
            if subclass:
                return LogfireEncoder._create_result_dict(
                    data_type=data_type, data=encoder(o), cls=o.__class__.__name__
                )
            else:
                return LogfireEncoder._create_result_dict(data_type=data_type, data=encoder(o))

        return type_encoder

    @cached_property
    def encoder_by_type(self) -> dict[type[Any], EncoderFunction]:
        lookup: dict[type[Any], EncoderFunction] = {
            set: self._build_default_encoder('set', list),
            bytes: self._bytes_encoder,
            datetime.date: self._build_default_encoder('date', lambda d: d.isoformat()),
            datetime.datetime: self._build_default_encoder('datetime', lambda d: d.isoformat()),
            datetime.time: self._build_default_encoder('time', lambda d: d.isoformat()),
            datetime.timedelta: self._build_default_encoder('timedelta', lambda td: td.total_seconds()),
            Decimal: self._build_default_encoder('Decimal', str),
            Enum: self._build_cls_encoder('Enum', lambda o: o.value),
            frozenset: self._build_default_encoder('frozenset', list),
            deque: self._build_default_encoder('deque', list),
            GeneratorType: self._build_default_encoder('generator', repr),
            IPv4Address: self._build_default_encoder('IPv4Address', str),
            IPv4Interface: self._build_default_encoder('IPv4Interface', str),
            IPv4Network: self._build_default_encoder('IPv4Network', str),
            IPv6Address: self._build_default_encoder('IPv6Address', str),
            IPv6Interface: self._build_default_encoder('IPv6Interface', str),
            IPv6Network: self._build_default_encoder('IPv6Network', str),
            PosixPath: self._build_default_encoder('PosixPath', str),
            Pattern: self._build_default_encoder('Pattern', lambda o: o.pattern),
            UUID: self._uuid_encoder,
            Exception: self._build_cls_encoder('Exception', str),
        }
        if pydantic:
            lookup.update(
                {
                    pydantic.AnyUrl: self._build_default_encoder('Url', str),
                    pydantic.NameEmail: self._build_default_encoder('NameEmail', str),
                    pydantic.SecretBytes: self._build_default_encoder('SecretBytes', str),
                    pydantic.SecretStr: self._build_default_encoder('SecretStr', str),
                    pydantic.BaseModel: self._build_cls_encoder('BaseModel', lambda o: o.model_dump()),
                }
            )
        # TODO(Samuel): add other popular 3rd party types here if they're installed,
        #  in particular: attrs, sqlalchemy, pandas, numpy
        return lookup

    def encode(self, o: Any) -> Any:
        if isinstance(o, tuple):
            return super().encode({'$__datatype__': 'tuple', 'data': o})
        return super().encode(o)

    def default(self, o: Any) -> Any:
        if dataclasses.is_dataclass(o):
            return self._cls_encoder('dataclass', dataclasses.asdict, o)
        elif isinstance(o, Mapping):
            return self._cls_encoder('Mapping', dict, o)

        # Check the class type and its superclasses for a matching encoder
        for i, base in enumerate(o.__class__.__mro__[:-1]):
            try:
                encoder = self.encoder_by_type[base]
            except KeyError:
                pass
            else:
                return encoder(o, i > 0)

        if isinstance(o, Sequence):
            return self._cls_encoder('Sequence', list, o)

        return self._cls_encoder('unknown', repr, o)


def logfire_json_dumps(obj: Any) -> str:
    return json.dumps(obj, cls=LogfireEncoder, separators=(',', ':'))


def _traceback_default(obj: Any):
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    else:
        raise TypeError(f"Object of type '{obj.__class__.__name__}' is not JSON serializable")


def json_dumps_traceback(obj: Any) -> str:
    """
    Specifically for converting rich tracebacks to JSON, where dataclasses need to be converted to dicts.
    """
    return json.dumps(obj, default=_traceback_default)
