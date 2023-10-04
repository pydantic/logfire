import json
import re
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from dirty_equals import IsInt
from pydantic import AnyUrl, BaseModel, FilePath, NameEmail, SecretBytes, SecretStr
from pydantic.dataclasses import dataclass as pydantic_dataclass

from logfire import Logfire
from logfire._flatten import Flatten

from .conftest import TestExporter


class MyModel(BaseModel):
    x: str
    y: int
    u: AnyUrl


@dataclass
class MyDataclass:
    t: int


@pydantic_dataclass
class MyPydanticDataclass:
    p: int


class MySequence(Sequence):
    def __len__(self):
        return 2

    def __getitem__(self, key):
        if key == 0:
            return 1
        elif key == 1:
            return 2
        else:
            raise IndexError()


class MyMapping(Mapping):
    def __init__(self, d):
        self._d = d

    def __getitem__(self, key):
        return self._d[key]

    def __iter__(self):
        return iter(self._d)

    def __len__(self):
        return len(self._d)


class MyArbitraryType:
    def __init__(self, x: int) -> None:
        self.x = x

    def __repr__(self) -> str:
        return f'MyArbitraryType({self.x})'


class MyBytes(bytes):
    pass


@pytest.mark.parametrize(
    'value,value_repr,value_json',
    [
        (['a', 1, True], "['a', 1, True]", '["a",1,true]'),
        ({'k1': 'v1', 'k2': 2}, "{'k1': 'v1', 'k2': 2}", '{"k1":"v1","k2":2}'),
        (b'test bytes', "b'test bytes'", '{"$__datatype__":"bytes","data":"test bytes"}'),
        ((1, 2, 'b'), "(1, 2, 'b')", '{"$__datatype__":"tuple","data":[1,2,"b"]}'),
        (set(['s']), "{'s'}", '{"$__datatype__":"set","data":["s"]}'),
        (frozenset(['f']), "frozenset({'f'})", '{"$__datatype__":"frozenset","data":["f"]}'),
        (Decimal('1.7'), '1.7', '{"$__datatype__":"Decimal","data":"1.7"}'),
        (date(2023, 1, 1), '2023-01-01', '{"$__datatype__":"date","data":"2023-01-01"}'),
        (
            datetime(2023, 1, 1, 10, 10),
            '2023-01-01 10:10:00',
            '{"$__datatype__":"datetime","data":"2023-01-01T10:10:00"}',
        ),
        (time(12, 10), '12:10:00', '{"$__datatype__":"time","data":"12:10:00"}'),
        (timedelta(1, seconds=3672), '1 day, 1:01:12', '{"$__datatype__":"timedelta","data":90072.0}'),
        (
            Enum('Color', ['RED', 'GREEN', 'BLUE']).BLUE,
            'Color.BLUE',
            '{"$__datatype__":"enum","data":3,"cls":"Color"}',
        ),
        (deque([4, 5]), 'deque([4, 5])', '{"$__datatype__":"deque","data":[4,5]}'),
        (IPv4Address('127.0.0.1'), '127.0.0.1', '{"$__datatype__":"IPv4Address","data":"127.0.0.1"}'),
        (IPv4Interface('192.0.2.5/24'), '192.0.2.5/24', '{"$__datatype__":"IPv4Interface","data":"192.0.2.5/24"}'),
        (IPv4Network('192.0.2.0/24'), '192.0.2.0/24', '{"$__datatype__":"IPv4Network","data":"192.0.2.0/24"}'),
        (IPv6Address('2001:db8::1000'), '2001:db8::1000', '{"$__datatype__":"IPv6Address","data":"2001:db8::1000"}'),
        (
            IPv6Interface('2001:db8::1000/128'),
            '2001:db8::1000/128',
            '{"$__datatype__":"IPv6Interface","data":"2001:db8::1000/128"}',
        ),
        (
            IPv6Network('2001:db8::1000/128'),
            '2001:db8::1000/128',
            '{"$__datatype__":"IPv6Network","data":"2001:db8::1000/128"}',
        ),
        (
            NameEmail(name='John Doe', email='john.doe@mail.com'),
            'John Doe <john.doe@mail.com>',
            '{"$__datatype__":"NameEmail","data":"John Doe <john.doe@mail.com>"}',
        ),
        (Path('/tmp/test.py'), '/tmp/test.py', '{"$__datatype__":"PosixPath","data":"/tmp/test.py"}'),
        (FilePath(__file__), '', f'{{"$__datatype__":"PosixPath","data":"{__file__}"}}'),
        (re.compile('test'), "re.compile('test')", '{"$__datatype__":"Pattern","data":"test"}'),
        (SecretBytes(b'secret bytes'), "b'**********'", '{"$__datatype__":"SecretBytes","data":"b\'**********\'"}'),
        (SecretStr('secret str'), '**********', '{"$__datatype__":"SecretStr","data":"**********"}'),
        (
            UUID('7265bc22-ccb0-4ee2-97f0-5dd206f01ae4'),
            '7265bc22-ccb0-4ee2-97f0-5dd206f01ae4',
            '{"$__datatype__":"UUID","data":"7265bc22-ccb0-4ee2-97f0-5dd206f01ae4","version":4}',
        ),
        (
            MyModel(x='x', y=10, u='http://test.com'),
            "x='x' y=10 u=Url('http://test.com/')",
            '{"$__datatype__":"BaseModel","data":{"x":"x","y":10,"u":{"$__datatype__":"Url","data":"http://test.com/"}},"cls":"MyModel"}',
        ),
        (
            MyDataclass(10),
            'MyDataclass(t=10)',
            '{"$__datatype__":"dataclass","data":{"t":10},"cls":"MyDataclass"}',
        ),
        (
            MyPydanticDataclass(20),
            'MyPydanticDataclass(p=20)',
            '{"$__datatype__":"dataclass","data":{"p":20},"cls":"MyPydanticDataclass"}',
        ),
        (
            ValueError('Test value error'),
            'Test value error',
            '{"$__datatype__":"Exception","data":"Test value error","cls":"ValueError"}',
        ),
        (
            MyMapping({'foo': 'bar'}),
            '<tests.test_json_args.MyMapping object at',
            '{"$__datatype__":"Mapping","data":{"foo":"bar"},"cls":"MyMapping"}',
        ),
        (range(4), 'range(0, 4)', '{"$__datatype__":"Sequence","data":[0,1,2,3],"cls":"range"}'),
        (
            MySequence(),
            '<tests.test_json_args.MySequence object at',
            '{"$__datatype__":"Sequence","data":[1,2],"cls":"MySequence"}',
        ),
        (
            MyArbitraryType(12),
            'MyArbitraryType(12)',
            '{"$__datatype__":"MyArbitraryType","data":"MyArbitraryType(12)","cls":"MyArbitraryType"}',
        ),
        (
            MyBytes(b'test bytes'),
            "b'test bytes'",
            '{"$__datatype__":"type","data":"test bytes","subclass":"MyBytes"}',
        ),
    ],
)
def test_log_non_scalar_args(logfire: Logfire, exporter: TestExporter, value, value_repr, value_json) -> None:
    logfire.info('test message {var=}', var=value)

    logfire._config.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.name.startswith(f'test message var={value_repr}')
    assert s.attributes['var__JSON'] == value_json


@pytest.mark.parametrize(
    'value,attributes',
    [
        pytest.param(
            Flatten({'a': 1, 'b': 2}),
            {
                'var.a': 1,
                'var.b': 2,
                'logfire.log_type': 'log',
                'logfire.level': 'info',
                'logfire.msg_template': 'test message {var=}',
                'logfire.lineno': IsInt(),
                'logfire.filename': 'src/packages/logfire/tests/test_json_args.py',
            },
            id='flatten_dict',
        ),
        pytest.param(
            Flatten([3, 2]),
            {
                'var.0': 3,
                'var.1': 2,
                'logfire.log_type': 'log',
                'logfire.level': 'info',
                'logfire.msg_template': 'test message {var=}',
                'logfire.lineno': IsInt(),
                'logfire.filename': 'src/packages/logfire/tests/test_json_args.py',
            },
            id='flatten_list',
        ),
        pytest.param(
            Flatten({'a': {'b': {'c': [1, 2]}}}),
            {
                'var.a__JSON': '{"b":{"c":[1,2]}}',
                'logfire.log_type': 'log',
                'logfire.level': 'info',
                'logfire.msg_template': 'test message {var=}',
                'logfire.lineno': IsInt(),
                'logfire.filename': 'src/packages/logfire/tests/test_json_args.py',
            },
            id='flatten_nested_dict',
        ),
        pytest.param(
            Flatten([{'a': 1}, {'b': 2}]),
            {
                'var.0__JSON': '{"a":1}',
                'var.1__JSON': '{"b":2}',
                'logfire.log_type': 'log',
                'logfire.level': 'info',
                'logfire.lineno': IsInt(),
                'logfire.msg_template': 'test message {var=}',
                'logfire.filename': 'src/packages/logfire/tests/test_json_args.py',
            },
            id='nested_list',
        ),
    ],
)
def test_log_flatten(logfire: Logfire, exporter: TestExporter, value: Flatten, attributes: dict[str, Any]) -> None:
    logfire.info('test message {var=}', var=value)

    logfire._config.provider.force_flush()
    s = exporter.exported_spans[0]

    # insert_assert(json.loads(s.to_json())['attributes'])
    assert json.loads(s.to_json())['attributes'] == attributes


def test_log_dataclass_arg(logfire: Logfire, exporter: TestExporter) -> None:
    logfire.info('test message {dc.t} repr = {dc}', dc=MyDataclass(t=1))

    logfire._config.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.name == 'test message 1 repr = MyDataclass(t=1)'
    assert s.attributes['dc__JSON'] == '{"$__datatype__":"dataclass","data":{"t":1},"cls":"MyDataclass"}'


def test_log_generator_arg(logfire: Logfire, exporter: TestExporter) -> None:
    def generator():
        yield from range(3)

    logfire.info('test message {var=}', var=generator())

    logfire._config.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.name.startswith('test message var=<generator object test_log_generator_arg.<locals>.generator')
    attr_value = s.attributes['var__JSON']
    assert '"$__datatype__":"generator"' in attr_value
    assert 'generator object test_log_generator_arg.<locals>.generator' in attr_value


def test_instrument_generator_arg(logfire: Logfire, exporter: TestExporter) -> None:
    def generator():
        yield from range(3)

    @logfire.instrument('test message {var=}')
    def hello_world(var):
        pass

    assert hello_world(generator()) is None

    logfire._config.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.name.startswith('test message var=<generator object test_instrument_generator_arg.<locals>.generator')
    s.attributes['var__JSON'] == '{"$__datatype__": "generator", "data": [0, 1, 2]}'


def test_log_non_scalar_complex_args(logfire: Logfire, exporter: TestExporter) -> None:
    class MyModel(BaseModel):
        x: str
        y: datetime

    model = MyModel(x='x', y=datetime(2023, 1, 1))

    @dataclass
    class MyDataclass:
        t: int

    dc = MyDataclass(10)

    @pydantic_dataclass
    class MyPydanticDataclass:
        p: int

    pdc = MyPydanticDataclass(20)

    logfire.info(
        'test message {complex_list=} {complex_dict=}',
        complex_list=['a', 1, model, dc, pdc],
        complex_dict={'k1': 'v1', 'model': model, 'dataclass': dc, 'pydantic_dataclass': pdc},
    )

    logfire._config.provider.force_flush()
    s = exporter.exported_spans[0]

    # insert_assert(dict(s.attributes))
    assert dict(s.attributes) == {
        'complex_list__JSON': (
            '["a",1,'
            '{"$__datatype__":"BaseModel","data":{"x":"x","y":{"$__datatype__":"datetime","data":"2023-01-01T00:00:00"}},"cls":"MyModel"},'
            '{"$__datatype__":"dataclass","data":{"t":10},"cls":"MyDataclass"},'
            '{"$__datatype__":"dataclass","data":{"p":20},"cls":"MyPydanticDataclass"}]'
        ),
        'complex_dict__JSON': (
            '{"k1":"v1",'
            '"model":{"$__datatype__":"BaseModel","data":{"x":"x","y":{"$__datatype__":"datetime","data":"2023-01-01T00:00:00"}},"cls":"MyModel"},'
            '"dataclass":{"$__datatype__":"dataclass","data":{"t":10},"cls":"MyDataclass"},'
            '"pydantic_dataclass":{"$__datatype__":"dataclass","data":{"p":20},"cls":"MyPydanticDataclass"}}'
        ),
        'logfire.log_type': 'log',
        'logfire.level': 'info',
        'logfire.msg_template': 'test message {complex_list=} {complex_dict=}',
        'logfire.lineno': IsInt(),
        'logfire.filename': 'src/packages/logfire/tests/test_json_args.py',
    }
