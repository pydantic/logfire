import dataclasses
import datetime
import json
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from enum import Enum
from functools import cached_property, partial
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import PosixPath
from re import Pattern
from types import GeneratorType
from typing import Any
from uuid import UUID

try:
    import pydantic
except ImportError:
    # pydantic is not installed, possible since it's not a dependency
    # don't add the types to the lookup logic
    pydantic = None

__all__ = 'LogfireEncoder', 'logfire_json_dumps', 'json_dumps_traceback'


class LogfireEncoder(json.JSONEncoder):
    @staticmethod
    def _create_result_dict(data_type: str, data: Any, **kwargs: Any) -> dict[str, Any]:
        return {'$__datatype__': data_type, 'data': data, **kwargs}

    @staticmethod
    def _default_encoder(encoder: Callable[[Any], Any], o: Any, subclass: Any = None) -> dict[str, Any]:
        if subclass:
            return LogfireEncoder._create_result_dict(
                data_type=subclass.__class__.__name__, data=encoder(o), subclass=o.__class__.__name__
            )

        return LogfireEncoder._create_result_dict(data_type=o.__class__.__name__, data=encoder(o))

    @staticmethod
    def _cls_encoder(encoder: Callable[[Any], Any], var_type: str, o: Any, subclass: Any = None) -> dict[str, Any]:
        return LogfireEncoder._create_result_dict(data_type=var_type, data=encoder(o), cls=o.__class__.__name__)

    @staticmethod
    def _uuid_encoder(encoder: Callable[[Any], Any], o: Any, subclass: Any = None) -> dict[str, Any]:
        return LogfireEncoder._create_result_dict(data_type=o.__class__.__name__, data=encoder(o), version=o.version)

    @cached_property
    def encoder_by_type(self) -> dict[type[Any], Callable[[Any], Any]]:
        lookup: dict[type[Any], Callable[[Any], Any]] = {
            set: partial(self._default_encoder, list),
            bytes: partial(self._default_encoder, lambda o: o.decode()),
            datetime.date: partial(self._default_encoder, lambda d: d.isoformat()),
            datetime.datetime: partial(self._default_encoder, lambda d: d.isoformat()),
            datetime.time: partial(self._default_encoder, lambda d: d.isoformat()),
            datetime.timedelta: partial(self._default_encoder, lambda td: td.total_seconds()),
            Decimal: partial(self._default_encoder, str),
            Enum: partial(self._cls_encoder, lambda o: o.value, 'enum'),
            frozenset: partial(self._default_encoder, list),
            deque: partial(self._default_encoder, list),
            GeneratorType: partial(self._default_encoder, repr),
            IPv4Address: partial(self._default_encoder, str),
            IPv4Interface: partial(self._default_encoder, str),
            IPv4Network: partial(self._default_encoder, str),
            IPv6Address: partial(self._default_encoder, str),
            IPv6Interface: partial(self._default_encoder, str),
            IPv6Network: partial(self._default_encoder, str),
            PosixPath: partial(self._default_encoder, str),
            Pattern: partial(self._default_encoder, lambda o: o.pattern),
            UUID: partial(self._uuid_encoder, str),
            Exception: partial(self._cls_encoder, str, 'Exception'),
        }
        if pydantic:
            lookup.update(
                {
                    pydantic.AnyUrl: partial(self._default_encoder, str),
                    pydantic.NameEmail: partial(self._default_encoder, str),
                    pydantic.SecretBytes: partial(self._default_encoder, str),
                    pydantic.SecretStr: partial(self._default_encoder, str),
                    pydantic.BaseModel: partial(self._cls_encoder, lambda o: o.model_dump(), 'BaseModel'),
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
            return self._cls_encoder(dataclasses.asdict, 'dataclass', o)
        elif isinstance(o, Mapping):
            return self._cls_encoder(dict, 'Mapping', o)

        # Check the class type and its superclasses for a matching encoder
        subclass = None
        for i, base in enumerate(o.__class__.__mro__[:-1]):
            try:
                encoder = self.encoder_by_type[base]
                if i > 0:
                    subclass = o.__class__.__mro__[i - 1]
                return encoder(o, subclass=subclass)  # type: ignore
            except KeyError:
                pass

        if isinstance(o, Sequence):
            return self._cls_encoder(list, 'Sequence', o)

        return self._cls_encoder(repr, o.__class__.__name__, o)


def logfire_json_dumps(obj: Any) -> str:
    # TODO(Samuel), we should add `, separators=(',', ':')`, https://linear.app/pydantic/issue/PYD-281
    return json.dumps(obj, cls=LogfireEncoder)


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
