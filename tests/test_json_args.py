from __future__ import annotations

import json
import re
import sys
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import Path
from typing import Any, Iterator, List, Mapping
from unittest.mock import MagicMock, Mock
from uuid import UUID

import numpy
import pandas
import pytest
from attrs import define
from dirty_equals import IsJson, IsStr
from inline_snapshot import snapshot
from pydantic import AnyUrl, BaseModel, ConfigDict, FilePath, NameEmail, SecretBytes, SecretStr
from pydantic.dataclasses import dataclass as pydantic_dataclass
from sqlalchemy import String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.orm.decl_api import MappedAsDataclass
from sqlalchemy.sql.schema import ForeignKey
from sqlmodel import SQLModel

import logfire
from logfire.testing import TestExporter

if sys.version_info >= (3, 11):  # pragma: no branch
    from enum import StrEnum
else:  # pragma: no cover

    class StrEnum(str, Enum): ...


pandas.set_option('display.max_columns', 10)
pandas.set_option('display.max_rows', 20)

pydantic_model_config = ConfigDict(plugin_settings={'logfire': {'record': 'off'}}, extra='allow')


class MyModel(BaseModel):
    model_config = pydantic_model_config
    x: str
    y: int
    u: AnyUrl


@dataclass(frozen=True)
class MyDataclass:
    t: int


@pydantic_dataclass(config=pydantic_model_config)
class MyPydanticDataclass:
    p: int


@dataclass
class MyComplexDataclass:
    t: MyDataclass


@pydantic_dataclass(config=pydantic_model_config)
class MyPydanticComplexDataclass:
    t: MyPydanticDataclass


@dataclass
class MyReprDataclass:
    in_repr: int
    not_in_repr: MyDataclass = field(repr=False)


class MySQLModel(SQLModel):
    s: int


class Generator:
    def __repr__(self) -> str:
        return 'Generator()'

    def __iter__(self) -> Iterator[int]:
        yield from range(3)  # pragma: no cover


def generator() -> Iterator[int]:
    yield from range(3)  # pragma: no cover


gen = generator()


if sys.version_info >= (3, 9):  # pragma: no branch
    _MySequence = Sequence[int]
    _ListSubclass = list[int]
else:  # pragma: no cover
    _MySequence = Sequence
    _ListSubclass = list


class MySequence(_MySequence):
    def __len__(self):
        return 2  # pragma: no cover

    def __getitem__(self, key: int) -> int:  # type: ignore
        if key == 0:
            return 1
        elif key == 1:
            return 2
        else:
            raise IndexError()


class MyMapping(Mapping[str, Any]):
    def __init__(self, d: Any):
        self._d = d

    def __getitem__(self, key: str) -> Any:
        return self._d[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._d)

    def __len__(self):  # pragma: no cover
        return len(self._d)


class MyArbitraryType:
    def __init__(self, x: int) -> None:
        self.x = x

    def __repr__(self) -> str:
        return f'MyArbitraryType({self.x})'


class MyBytes(bytes):
    pass


@define
class AttrsType:
    x: int
    y: int
    z: AttrsType | None = None


@define
class AttrsError(Exception):
    code: int


class ListSubclass(_ListSubclass): ...


class StrSubclass(str):
    pass


ANYURL_REPR_CLASSNAME = repr(AnyUrl('http://test.com')).split('(')[0]


@pytest.mark.parametrize(
    'value,value_repr,value_json,json_schema',
    [
        pytest.param(
            ['a', 1, True],
            "['a', 1, True]",
            '["a",1,true]',
            {'type': 'array'},
            id='list',
        ),
        pytest.param(
            [],
            '[]',
            '[]',
            {'type': 'array'},
            id='empty_list',
        ),
        pytest.param(
            [MyDataclass(10), MyDataclass(20), MyDataclass(30)],
            '[MyDataclass(t=10), MyDataclass(t=20), MyDataclass(t=30)]',
            '[{"t":10},{"t":20},{"t":30}]',
            {
                'type': 'array',
                'items': {'type': 'object', 'title': 'MyDataclass', 'x-python-datatype': 'dataclass'},
            },
            id='list_with_items_key',
        ),
        pytest.param(
            ['a', 1, True, MyDataclass(10)],
            "['a', 1, True, MyDataclass(t=10)]",
            '["a",1,true,{"t":10}]',
            {
                'type': 'array',
                'prefixItems': [
                    {},
                    {},
                    {},
                    {'type': 'object', 'title': 'MyDataclass', 'x-python-datatype': 'dataclass'},
                ],
            },
            id='list_with_complex_type',
        ),
        pytest.param(
            {'k1': 'v1', 'k2': 2},
            "{'k1': 'v1', 'k2': 2}",
            '{"k1":"v1","k2":2}',
            {'type': 'object'},
            id='dict',
        ),
        pytest.param(
            {MyDataclass(10): 1, MyDataclass(20): 2, MyDataclass(30): 3},
            '{MyDataclass(t=10): 1, MyDataclass(t=20): 2, MyDataclass(t=30): 3}',
            '{"MyDataclass(t=10)":1,"MyDataclass(t=20)":2,"MyDataclass(t=30)":3}',
            {'type': 'object'},
            id='dict_complex_keys',
        ),
        pytest.param(
            b'test bytes',
            "b'test bytes'",
            '"test bytes"',
            {'type': 'string', 'x-python-datatype': 'bytes'},
            id='bytes_utf8',
        ),
        pytest.param(
            b'\x81',
            "b'\\x81'",
            '"\\\\x81"',
            {'type': 'string', 'x-python-datatype': 'bytes'},
            id='bytes_base64',
        ),
        pytest.param(
            bytearray(b'test bytes'),
            "bytearray(b'test bytes')",
            '"test bytes"',
            {'type': 'string', 'x-python-datatype': 'bytearray'},
            id='bytearray',
        ),
        pytest.param(
            (1, 2, 'b'),
            "(1, 2, 'b')",
            '[1,2,"b"]',
            {'type': 'array', 'x-python-datatype': 'tuple'},
            id='tuple',
        ),
        pytest.param(
            (),
            '()',
            '[]',
            {'type': 'array', 'x-python-datatype': 'tuple'},
            id='empty_tuple',
        ),
        pytest.param(
            ListSubclass([1, 2, 3]),
            '[1, 2, 3]',
            '[1,2,3]',
            {'type': 'array', 'x-python-datatype': 'Sequence', 'title': 'ListSubclass'},
            id='ListSubclass',
        ),
        pytest.param(
            StrSubclass('test'),
            'test',
            'test',
            {},
        ),
        pytest.param(
            (MyDataclass(10), MyDataclass(20), MyDataclass(30)),
            '(MyDataclass(t=10), MyDataclass(t=20), MyDataclass(t=30))',
            '[{"t":10},{"t":20},{"t":30}]',
            {
                'type': 'array',
                'x-python-datatype': 'tuple',
                'items': {
                    'type': 'object',
                    'title': 'MyDataclass',
                    'x-python-datatype': 'dataclass',
                },
            },
            id='tuple_with_items_key',
        ),
        pytest.param(
            set(['s']),
            "{'s'}",
            '["s"]',
            {'type': 'array', 'x-python-datatype': 'set'},
            id='set',
        ),
        pytest.param(
            set([MyDataclass(10), MyDataclass(20), MyDataclass(30)]),
            '{MyDataclass(t=30), MyDataclass(t=20), MyDataclass(t=10)}',
            '[{"t":30},{"t":20},{"t":10}]',
            {'type': 'array', 'x-python-datatype': 'set'},
            id='set_with_items_key',
        ),
        pytest.param(
            frozenset(['f']),
            "frozenset({'f'})",
            '["f"]',
            {'type': 'array', 'x-python-datatype': 'frozenset'},
            id='frozenset',
        ),
        pytest.param(
            frozenset([MyDataclass(10), MyDataclass(20), MyDataclass(30)]),
            'frozenset({MyDataclass(t=30), MyDataclass(t=20), MyDataclass(t=10)})',
            '[{"t":30},{"t":20},{"t":10}]',
            {'type': 'array', 'x-python-datatype': 'frozenset'},
            id='frozenset_with_items_key',
        ),
        pytest.param(
            Decimal('1.7'),
            '1.7',
            '"1.7"',
            {'type': 'string', 'format': 'decimal', 'x-python-datatype': 'Decimal'},
            id='decimal',
        ),
        pytest.param(
            date(2023, 1, 1),
            '2023-01-01',
            '"2023-01-01"',
            {'type': 'string', 'format': 'date', 'x-python-datatype': 'date'},
            id='date',
        ),
        pytest.param(
            datetime(2023, 1, 1, 10, 10),
            '2023-01-01 10:10:00',
            '"2023-01-01T10:10:00"',
            {'type': 'string', 'format': 'date-time', 'x-python-datatype': 'datetime'},
            id='datetime',
        ),
        pytest.param(
            time(12, 10),
            '12:10:00',
            '"12:10:00"',
            {'type': 'string', 'format': 'time', 'x-python-datatype': 'time'},
            id='time',
        ),
        pytest.param(
            timedelta(1, seconds=3672),
            '1 day, 1:01:12',
            '90072.0',
            {'type': 'string', 'x-python-datatype': 'timedelta'},
            id='timedelta',
        ),
        pytest.param(
            Enum('Color', ['RED', 'GREEN', 'BLUE']).BLUE,
            'Color.BLUE',
            '3',
            {
                'type': 'integer',
                'title': 'Color',
                'x-python-datatype': 'Enum',
                'enum': [1, 2, 3],
            },
            id='enum',
        ),
        pytest.param(
            {'enum': StrEnum('Color', ['RED', 'GREEN', 'BLUE']).BLUE},
            "{'enum': <Color.BLUE: 'blue'>}" if sys.version_info >= (3, 11) else "{'enum': <Color.BLUE: '3'>}",
            '{"enum":"blue"}' if sys.version_info >= (3, 11) else '{"enum":"3"}',
            {
                'type': 'object',
                'properties': {
                    'enum': {
                        'type': 'string',
                        'title': 'Color',
                        'x-python-datatype': 'Enum',
                        'enum': ['red', 'green', 'blue'] if sys.version_info >= (3, 11) else ['1', '2', '3'],
                    }
                },
            },
            id='str_enum',
        ),
        pytest.param(
            Enum('Color', {'RED': 1, 'GREEN': 'str', 'BLUE': MyDataclass(t=1)}).BLUE,
            'Color.BLUE',
            '{"t":1}',
            {
                'type': 'object',
                'title': 'Color',
                'x-python-datatype': 'Enum',
                'enum': [1, 'str', {'t': 1}],
            },
            id='enum_with_complex_values',
        ),
        pytest.param(
            deque([4, 5]),
            'deque([4, 5])',
            '[4,5]',
            {'type': 'array', 'x-python-datatype': 'deque'},
            id='deque',
        ),
        pytest.param(
            deque([MyDataclass(10), MyDataclass(20), MyDataclass(30)]),
            'deque([MyDataclass(t=10), MyDataclass(t=20), MyDataclass(t=30)])',
            '[{"t":10},{"t":20},{"t":30}]',
            {
                'type': 'array',
                'x-python-datatype': 'deque',
                'items': {
                    'type': 'object',
                    'title': 'MyDataclass',
                    'x-python-datatype': 'dataclass',
                },
            },
            id='deque_with_items_key',
        ),
        pytest.param(
            IPv4Address('127.0.0.1'),
            '127.0.0.1',
            '"127.0.0.1"',
            {'type': 'string', 'format': 'ipv4'},
            id='ipv4',
        ),
        pytest.param(
            IPv4Interface('192.0.2.5/24'),
            '192.0.2.5/24',
            '"192.0.2.5/24"',
            {'type': 'string', 'format': 'ipv4interface'},
        ),
        pytest.param(
            IPv4Network('192.0.2.0/24'),
            '192.0.2.0/24',
            '"192.0.2.0/24"',
            {'type': 'string', 'format': 'ipv4network'},
        ),
        pytest.param(
            IPv6Address('2001:db8::1000'),
            '2001:db8::1000',
            '"2001:db8::1000"',
            {'type': 'string', 'format': 'ipv6'},
        ),
        pytest.param(
            IPv6Interface('2001:db8::1000/128'),
            '2001:db8::1000/128',
            '"2001:db8::1000/128"',
            {'type': 'string', 'format': 'ipv6interface'},
        ),
        pytest.param(
            IPv6Network('2001:db8::1000/128'),
            '2001:db8::1000/128',
            '"2001:db8::1000/128"',
            {'type': 'string', 'format': 'ipv6network'},
        ),
        pytest.param(
            NameEmail(name='John Doe', email='john.doe@mail.com'),
            'John Doe <john.doe@mail.com>',
            '"John Doe <john.doe@mail.com>"',
            {'type': 'string', 'x-python-datatype': 'NameEmail'},
            id='name-email',
        ),
        pytest.param(
            Path('/tmp/test.py'),
            '/tmp/test.py',
            '"/tmp/test.py"',
            {'type': 'string', 'format': 'path', 'x-python-datatype': 'PosixPath'},
            id='path',
        ),
        pytest.param(
            FilePath(__file__),  # type: ignore
            __file__,
            f'"{__file__}"',
            {'type': 'string', 'format': 'path', 'x-python-datatype': 'PosixPath'},
            id='pydantic_file_path',
        ),
        pytest.param(
            re.compile('test'),
            "re.compile('test')",
            '"test"',
            {'type': 'string', 'format': 'regex'},
            id='regex',
        ),
        pytest.param(
            SecretBytes(b'secret bytes'),
            "b'**********'",
            '"b\'**********\'"',
            {'type': 'string', 'x-python-datatype': 'SecretBytes'},
            id='secret_bytes',
        ),
        pytest.param(
            SecretStr('secret str'),
            '**********',
            '"**********"',
            {'type': 'string', 'x-python-datatype': 'SecretStr'},
            id='secret_str',
        ),
        pytest.param(
            UUID('7265bc22-ccb0-4ee2-97f0-5dd206f01ae4'),
            '7265bc22-ccb0-4ee2-97f0-5dd206f01ae4',
            '"7265bc22-ccb0-4ee2-97f0-5dd206f01ae4"',
            {'type': 'string', 'format': 'uuid'},
            id='uuid',
        ),
        pytest.param(
            MyModel(x='x', y=10, u=AnyUrl('http://test.com')),
            f"x='x' y=10 u={ANYURL_REPR_CLASSNAME}('http://test.com/')",
            '{"x":"x","y":10,"u":"http://test.com/"}',
            {
                'type': 'object',
                'title': 'MyModel',
                'x-python-datatype': 'PydanticModel',
                'properties': {'u': {'type': 'string', 'x-python-datatype': ANYURL_REPR_CLASSNAME}},
            },
            id='pydantic_model',
        ),
        pytest.param(
            MyModel.model_validate(dict(x='x', y=10, u='http://test.com', extra_key=MyDataclass(10))),
            f"x='x' y=10 u={ANYURL_REPR_CLASSNAME}('http://test.com/')",
            '{"x":"x","y":10,"u":"http://test.com/","extra_key":{"t":10}}',
            {
                'type': 'object',
                'title': 'MyModel',
                'x-python-datatype': 'PydanticModel',
                'properties': {
                    'u': {'type': 'string', 'x-python-datatype': ANYURL_REPR_CLASSNAME},
                    'extra_key': {
                        'type': 'object',
                        'title': 'MyDataclass',
                        'x-python-datatype': 'dataclass',
                    },
                },
            },
            id='pydantic_model_with_extra',
        ),
        pytest.param(
            MySQLModel(s=10),
            's=10',
            '{"s":10}',
            {'type': 'object', 'title': 'MySQLModel', 'x-python-datatype': 'PydanticModel'},
        ),
        pytest.param(
            MyDataclass(10),
            'MyDataclass(t=10)',
            '{"t":10}',
            {'type': 'object', 'title': 'MyDataclass', 'x-python-datatype': 'dataclass'},
            id='dataclass',
        ),
        pytest.param(
            MyPydanticDataclass(20),
            'MyPydanticDataclass(p=20)',
            '{"p":20}',
            {'type': 'object', 'title': 'MyPydanticDataclass', 'x-python-datatype': 'dataclass'},
            id='pydantic_dataclass',
        ),
        pytest.param(
            MyComplexDataclass(t=MyDataclass(10)),
            'MyComplexDataclass(t=MyDataclass(t=10))',
            '{"t":{"t":10}}',
            {
                'type': 'object',
                'title': 'MyComplexDataclass',
                'x-python-datatype': 'dataclass',
                'properties': {
                    't': {
                        'type': 'object',
                        'title': 'MyDataclass',
                        'x-python-datatype': 'dataclass',
                    }
                },
            },
            id='complex_dataclass',
        ),
        pytest.param(
            MyPydanticComplexDataclass(t=MyPydanticDataclass(20)),
            'MyPydanticComplexDataclass(t=MyPydanticDataclass(p=20))',
            '{"t":{"p":20}}',
            {
                'type': 'object',
                'title': 'MyPydanticComplexDataclass',
                'x-python-datatype': 'dataclass',
                'properties': {
                    't': {
                        'type': 'object',
                        'title': 'MyPydanticDataclass',
                        'x-python-datatype': 'dataclass',
                    }
                },
            },
            id='pydantic_complex_dataclass',
        ),
        pytest.param(
            MyReprDataclass(in_repr=1, not_in_repr=MyDataclass(t=2)),
            'MyReprDataclass(in_repr=1)',
            '{"in_repr":1}',
            {'type': 'object', 'title': 'MyReprDataclass', 'x-python-datatype': 'dataclass'},
            id='repr_dataclass',
        ),
        pytest.param(
            ValueError('Test value error'),
            'Test value error',
            '"Test value error"',
            {'type': 'object', 'title': 'ValueError', 'x-python-datatype': 'Exception'},
            id='exception',
        ),
        pytest.param(
            Generator(),
            'Generator()',
            '"Generator()"',
            {'type': 'object', 'x-python-datatype': 'unknown'},
            id='generator_class',
        ),
        pytest.param(
            gen,
            '<generator object generator at ',
            f'"{repr(gen)}"',
            {'type': 'array', 'title': 'generator', 'x-python-datatype': 'generator'},
            id='generator',
        ),
        pytest.param(
            MyMapping({'foo': 'bar'}),
            '<tests.test_json_args.MyMapping object at',
            '{"foo":"bar"}',
            {'type': 'object', 'title': 'MyMapping', 'x-python-datatype': 'Mapping'},
            id='mapping',
        ),
        pytest.param(
            range(4),
            'range(0, 4)',
            '[0,1,2,3]',
            {'type': 'array', 'x-python-datatype': 'range'},
            id='range',
        ),
        pytest.param(
            MySequence(),
            '<tests.test_json_args.MySequence object at',
            '[1,2]',
            {'type': 'array', 'title': 'MySequence', 'x-python-datatype': 'Sequence'},
            id='sequence',
        ),
        pytest.param(
            MyArbitraryType(12),
            'MyArbitraryType(12)',
            '"MyArbitraryType(12)"',
            {'type': 'object', 'x-python-datatype': 'unknown'},
            id='arbitrary',
        ),
        pytest.param(
            MyBytes(b'test bytes'),
            "b'test bytes'",
            '"test bytes"',
            {
                'type': 'string',
                'title': 'MyBytes',
                'x-python-datatype': 'bytes',
            },
            id='custom_bytes_class',
        ),
        pytest.param(
            pandas.DataFrame(data={'col1': [1, 2], 'col2': [3, 4]}),
            '   col1  col2\n0     1     3\n1     2     4',
            '[[1,3],[2,4]]',
            {
                'type': 'array',
                'x-python-datatype': 'DataFrame',
                'x-columns': ['col1', 'col2'],
                'x-indices': [0, 1],
                'x-row-count': 2,
                'x-column-count': 2,
            },
            id='dataframe',
        ),
        pytest.param(
            pandas.DataFrame(
                data={f'col{i}': [i * j for j in range(1, 23)] for i in range(1, 13)},
                index=[f'i{x}' for x in range(1, 23)],  # type: ignore
            ),
            '     col1  col2  col3  col4  col5  ...  col8  col9  col10  col'
            '...'
            '  ...   176   198    220    242    264\n\n[22 rows x 12 columns]',
            '[[1,2,3,4,5,8,9,10,11,12],'
            '[2,4,6,8,10,16,18,20,22,24],'
            '[3,6,9,12,15,24,27,30,33,36],'
            '[4,8,12,16,20,32,36,40,44,48],'
            '[5,10,15,20,25,40,45,50,55,60],'
            '[6,12,18,24,30,48,54,60,66,72],'
            '[7,14,21,28,35,56,63,70,77,84],'
            '[8,16,24,32,40,64,72,80,88,96],'
            '[9,18,27,36,45,72,81,90,99,108],'
            '[10,20,30,40,50,80,90,100,110,120],'
            '[13,26,39,52,65,104,117,130,143,156],'
            '[14,28,42,56,70,112,126,140,154,168],'
            '[15,30,45,60,75,120,135,150,165,180],'
            '[16,32,48,64,80,128,144,160,176,192],'
            '[17,34,51,68,85,136,153,170,187,204],'
            '[18,36,54,72,90,144,162,180,198,216],'
            '[19,38,57,76,95,152,171,190,209,228],'
            '[20,40,60,80,100,160,180,200,220,240],'
            '[21,42,63,84,105,168,189,210,231,252],'
            '[22,44,66,88,110,176,198,220,242,264]]',
            {
                'type': 'array',
                'x-python-datatype': 'DataFrame',
                'x-columns': ['col1', 'col2', 'col3', 'col4', 'col5', 'col8', 'col9', 'col10', 'col11', 'col12'],
                'x-indices': [
                    'i1',
                    'i2',
                    'i3',
                    'i4',
                    'i5',
                    'i6',
                    'i7',
                    'i8',
                    'i9',
                    'i10',
                    'i13',
                    'i14',
                    'i15',
                    'i16',
                    'i17',
                    'i18',
                    'i19',
                    'i20',
                    'i21',
                    'i22',
                ],
                'x-row-count': 22,
                'x-column-count': 12,
            },
            id='dataframe_big',
        ),
        pytest.param(
            numpy.array([[1, 2], [3, 4]]),
            '[[1 2]\n [3 4]]',
            '[[1,2],[3,4]]',
            {
                'type': 'array',
                'x-python-datatype': 'ndarray',
                'x-shape': [2, 2],
                'x-dtype': 'int64',
            },
            id='numpy_array',
        ),
        pytest.param(
            numpy.array([[i * j for j in range(1, 13)] for i in range(1, 23)]),
            '[[  1   2   3   4   5   6   7   8   9  10  11  12]\n'
            ' [  2   4  '
            '...'
            '0 231 252]\n'
            ' [ 22  44  66  88 110 132 154 176 198 220 242 264]]',
            '[[1,2,3,4,5,8,9,10,11,12],[2,4,6,8,10,16,18,20,22,24],[3,6,9,12,15,24,27,30,33,36],[4,8,12,16,20,32,36,40,44,48],[5,10,15,20,25,40,45,50,55,60],[18,36,54,72,90,144,162,180,198,216],[19,38,57,76,95,152,171,190,209,228],[20,40,60,80,100,160,180,200,220,240],[21,42,63,84,105,168,189,210,231,252],[22,44,66,88,110,176,198,220,242,264]]',
            {
                'type': 'array',
                'x-python-datatype': 'ndarray',
                'x-shape': [22, 12],
                'x-dtype': 'int64',
            },
            id='numpy_array_2d',
        ),
        pytest.param(
            numpy.array([[[i * j * k for j in range(1, 13)] for i in range(1, 13)] for k in range(1, 13)]),
            '[[[   1    2    3 ...   10   11   12]\n'
            '  [   2    4    6 ...   '
            '...'
            '96 ... 1320 1452 1584]\n'
            '  [ 144  288  432 ... 1440 1584 1728]]]',
            '[[[1,2,3,4,5,8,9,10,11,12],[2,4,6,8,10,16,18,20,22,24],[3,6,9,12,15,24,27,30,33,36],[4,8,12,16,20,32,36,40,44,48],[5,10,15,20,25,40,45,50,55,60],[8,16,24,32,40,64,72,80,88,96],[9,18,27,36,45,72,81,90,99,108],[10,20,30,40,50,80,90,100,110,120],[11,22,33,44,55,88,99,110,121,132],[12,24,36,48,60,96,108,120,132,144]],'
            '[[2,4,6,8,10,16,18,20,22,24],[4,8,12,16,20,32,36,40,44,48],[6,12,18,24,30,48,54,60,66,72],[8,16,24,32,40,64,72,80,88,96],[10,20,30,40,50,80,90,100,110,120],[16,32,48,64,80,128,144,160,176,192],[18,36,54,72,90,144,162,180,198,216],[20,40,60,80,100,160,180,200,220,240],[22,44,66,88,110,176,198,220,242,264],[24,48,72,96,120,192,216,240,264,288]],'
            '[[3,6,9,12,15,24,27,30,33,36],[6,12,18,24,30,48,54,60,66,72],[9,18,27,36,45,72,81,90,99,108],[12,24,36,48,60,96,108,120,132,144],[15,30,45,60,75,120,135,150,165,180],[24,48,72,96,120,192,216,240,264,288],[27,54,81,108,135,216,243,270,297,324],[30,60,90,120,150,240,270,300,330,360],[33,66,99,132,165,264,297,330,363,396],[36,72,108,144,180,288,324,360,396,432]],'
            '[[4,8,12,16,20,32,36,40,44,48],[8,16,24,32,40,64,72,80,88,96],[12,24,36,48,60,96,108,120,132,144],[16,32,48,64,80,128,144,160,176,192],[20,40,60,80,100,160,180,200,220,240],[32,64,96,128,160,256,288,320,352,384],[36,72,108,144,180,288,324,360,396,432],[40,80,120,160,200,320,360,400,440,480],[44,88,132,176,220,352,396,440,484,528],[48,96,144,192,240,384,432,480,528,576]],'
            '[[5,10,15,20,25,40,45,50,55,60],[10,20,30,40,50,80,90,100,110,120],[15,30,45,60,75,120,135,150,165,180],[20,40,60,80,100,160,180,200,220,240],[25,50,75,100,125,200,225,250,275,300],[40,80,120,160,200,320,360,400,440,480],[45,90,135,180,225,360,405,450,495,540],[50,100,150,200,250,400,450,500,550,600],[55,110,165,220,275,440,495,550,605,660],[60,120,180,240,300,480,540,600,660,720]],'
            '[[8,16,24,32,40,64,72,80,88,96],[16,32,48,64,80,128,144,160,176,192],[24,48,72,96,120,192,216,240,264,288],[32,64,96,128,160,256,288,320,352,384],[40,80,120,160,200,320,360,400,440,480],[64,128,192,256,320,512,576,640,704,768],[72,144,216,288,360,576,648,720,792,864],[80,160,240,320,400,640,720,800,880,960],[88,176,264,352,440,704,792,880,968,1056],[96,192,288,384,480,768,864,960,1056,1152]],'
            '[[9,18,27,36,45,72,81,90,99,108],[18,36,54,72,90,144,162,180,198,216],[27,54,81,108,135,216,243,270,297,324],[36,72,108,144,180,288,324,360,396,432],[45,90,135,180,225,360,405,450,495,540],[72,144,216,288,360,576,648,720,792,864],[81,162,243,324,405,648,729,810,891,972],[90,180,270,360,450,720,810,900,990,1080],[99,198,297,396,495,792,891,990,1089,1188],[108,216,324,432,540,864,972,1080,1188,1296]],'
            '[[10,20,30,40,50,80,90,100,110,120],[20,40,60,80,100,160,180,200,220,240],[30,60,90,120,150,240,270,300,330,360],[40,80,120,160,200,320,360,400,440,480],[50,100,150,200,250,400,450,500,550,600],[80,160,240,320,400,640,720,800,880,960],[90,180,270,360,450,720,810,900,990,1080],[100,200,300,400,500,800,900,1000,1100,1200],[110,220,330,440,550,880,990,1100,1210,1320],[120,240,360,480,600,960,1080,1200,1320,1440]],'
            '[[11,22,33,44,55,88,99,110,121,132],[22,44,66,88,110,176,198,220,242,264],[33,66,99,132,165,264,297,330,363,396],[44,88,132,176,220,352,396,440,484,528],[55,110,165,220,275,440,495,550,605,660],[88,176,264,352,440,704,792,880,968,1056],[99,198,297,396,495,792,891,990,1089,1188],[110,220,330,440,550,880,990,1100,1210,1320],[121,242,363,484,605,968,1089,1210,1331,1452],[132,264,396,528,660,1056,1188,1320,1452,1584]],'
            '[[12,24,36,48,60,96,108,120,132,144],[24,48,72,96,120,192,216,240,264,288],[36,72,108,144,180,288,324,360,396,432],[48,96,144,192,240,384,432,480,528,576],[60,120,180,240,300,480,540,600,660,720],[96,192,288,384,480,768,864,960,1056,1152],[108,216,324,432,540,864,972,1080,1188,1296],[120,240,360,480,600,960,1080,1200,1320,1440],[132,264,396,528,660,1056,1188,1320,1452,1584],[144,288,432,576,720,1152,1296,1440,1584,1728]]]',
            {
                'type': 'array',
                'x-python-datatype': 'ndarray',
                'x-shape': [12, 12, 12],
                'x-dtype': 'int64',
            },
            id='numpy_array_3d',
        ),
        pytest.param(
            numpy.matrix([[1, 2], [3, 4]]),
            '[[1 2]\n [3 4]]',
            '[[1,2],[3,4]]',
            {
                'type': 'array',
                'x-python-datatype': 'ndarray',
                'x-shape': [2, 2],
                'x-dtype': 'int64',
            },
            id='numpy_matrix',
        ),
        pytest.param(
            AttrsType(1, 2),
            'AttrsType(x=1, y=2, z=None)',
            '{"x":1,"y":2,"z":null}',
            {'type': 'object', 'title': 'AttrsType', 'x-python-datatype': 'attrs'},
            id='attrs-simple',
        ),
        pytest.param(
            AttrsError(404),
            '404',
            '{"code":404}',
            {'type': 'object', 'title': 'AttrsError', 'x-python-datatype': 'attrs'},
            id='attrs-error',
        ),
        pytest.param(
            AttrsType(1, 2, AttrsType(1, 2)),
            'AttrsType(x=1, y=2, z=AttrsType(x=1, y=2, z=None))',
            '{"x":1,"y":2,"z":{"x":1,"y":2,"z":null}}',
            {
                'type': 'object',
                'title': 'AttrsType',
                'x-python-datatype': 'attrs',
                'properties': {
                    'z': {
                        'type': 'object',
                        'title': 'AttrsType',
                        'x-python-datatype': 'attrs',
                    }
                },
            },
            id='attrs-nsted',
        ),
        pytest.param(
            [{str: bytes, int: float}],
            "[{<class 'str'>: <class 'bytes'>, <class 'int'>: <class 'float'>}]",
            '[{"<class \'str\'>":"<class \'bytes\'>","<class \'int\'>":"<class \'float\'>"}]',
            {
                'items': {
                    'properties': {
                        "<class 'int'>": {'type': 'object', 'x-python-datatype': 'unknown'},
                        "<class 'str'>": {'type': 'object', 'x-python-datatype': 'unknown'},
                    },
                    'type': 'object',
                },
                'type': 'array',
            },
            id='dict_of_types_in_list',
        ),
        pytest.param(
            [MyDataclass],
            "[<class 'tests.test_json_args.MyDataclass'>]",
            '["<class \'tests.test_json_args.MyDataclass\'>"]',
            {
                'items': {
                    'type': 'object',
                    'x-python-datatype': 'unknown',
                },
                'type': 'array',
            },
            id='list_of_dataclass_type',
        ),
    ],
)
def test_log_non_scalar_args(
    exporter: TestExporter,
    value: Any,
    value_repr: str,
    value_json: str,
    json_schema: str,
) -> None:
    logfire.info('test message {var=}', var=value)

    s = exporter.exported_spans[0]

    assert s.name == 'test message {var=}'
    assert s.attributes, "Span doesn't have attributes"
    assert isinstance(s.attributes['logfire.msg'], str)
    assert s.attributes['logfire.msg'].startswith(f'test message var={value_repr}')
    assert s.attributes['var'] == value_json
    assert json.loads(s.attributes['logfire.json_schema'])['properties']['var'] == json_schema  # type: ignore


class SABase(MappedAsDataclass, DeclarativeBase):
    pass


class SAModel(SABase):
    __tablename__ = 'model'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    models2: Mapped[List[SAModel2]] = relationship(back_populates='model', lazy='dynamic')  # noqa


class SAModel2(SABase):
    __tablename__ = 'model2'

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey('model.id'))
    model: Mapped[SAModel] = relationship(back_populates='models2')


def test_log_sqlalchemy_class(exporter: TestExporter) -> None:
    engine = create_engine('sqlite:///:memory:')
    session = Session(engine)
    SABase.metadata.create_all(engine)
    model = SAModel(1, 'test name', [])
    model2 = SAModel2(1, 1, model)
    session.add(model)
    session.add(model2)
    session.commit()

    var = session.query(SAModel).all()[0]
    var2 = session.query(SAModel2).all()[0]
    logfire.info('test message', var=var, var2=var2)
    engine.dispose()

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'test message',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test message',
                    'logfire.msg': 'test message',
                    'code.filepath': 'test_json_args.py',
                    'code.function': 'test_log_sqlalchemy_class',
                    'code.lineno': 123,
                    'var': '{"models2":"<deferred>","id":1,"name":"test name"}',
                    'var2': '{"model":"<deferred>","id":1,"model_id":1}',
                    'logfire.json_schema': '{"type":"object","properties":{"var":{"type":"object","title":"SAModel","x-python-datatype":"sqlalchemy"},"var2":{"type":"object","title":"SAModel2","x-python-datatype":"sqlalchemy"}}}',
                },
            }
        ]
    )


def test_log_non_scalar_complex_args(exporter: TestExporter) -> None:
    class MyModel(BaseModel):
        model_config = pydantic_model_config
        x: str
        y: datetime

    model = MyModel(x='x', y=datetime(2023, 1, 1))

    @dataclass
    class MyDataclass:
        t: int

    dc = MyDataclass(10)

    @pydantic_dataclass(config=pydantic_model_config)
    class MyPydanticDataclass:
        p: int

    pdc = MyPydanticDataclass(20)

    logfire.info(
        'test message {a=} {complex_list=} {complex_dict=}',
        a=1,
        complex_list=['a', 1, model, dc, pdc],
        complex_dict={'k1': 'v1', 'model': model, 'dataclass': dc, 'pydantic_dataclass': pdc},
    )

    assert exporter.exported_spans_as_dict(_include_pending_spans=True)[0]['attributes'] == snapshot(
        {
            'logfire.span_type': 'log',
            'logfire.level_num': 9,
            'logfire.msg_template': 'test message {a=} {complex_list=} {complex_dict=}',
            'logfire.msg': (
                'test message '
                'a=1 '
                "complex_list=['a', 1, MyModel(x='x', y=datetime.datetime(2023, 1, 1, 0, 0))"
                '...'
                'og_non_scalar_complex_args.<locals>.MyPydanticDataclass(p=20)] '
                "complex_dict={'k1': 'v1', 'model': MyModel(x='x', y=datetime.datetime(2023,"
                '...'
                'og_non_scalar_complex_args.<locals>.MyPydanticDataclass(p=20)}'
            ),
            'logfire.json_schema': '{"type":"object","properties":{"a":{},"complex_list":{"type":"array","prefixItems":[{},{},{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel","properties":{"y":{"type":"string","format":"date-time","x-python-datatype":"datetime"}}},{"type":"object","title":"MyDataclass","x-python-datatype":"dataclass"},{"type":"object","title":"MyPydanticDataclass","x-python-datatype":"dataclass"}]},"complex_dict":{"type":"object","properties":{"model":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel","properties":{"y":{"type":"string","format":"date-time","x-python-datatype":"datetime"}}},"dataclass":{"type":"object","title":"MyDataclass","x-python-datatype":"dataclass"},"pydantic_dataclass":{"type":"object","title":"MyPydanticDataclass","x-python-datatype":"dataclass"}}}}}',
            'code.filepath': 'test_json_args.py',
            'code.lineno': 123,
            'code.function': 'test_log_non_scalar_complex_args',
            'a': 1,
            'complex_list': '["a",1,{"x":"x","y":"2023-01-01T00:00:00"},{"t":10},{"p":20}]',
            'complex_dict': '{"k1":"v1","model":{"x":"x","y":"2023-01-01T00:00:00"},"dataclass":{"t":10},"pydantic_dataclass":{"p":20}}',
        }
    )


def test_log_dicts_and_lists(exporter: TestExporter) -> None:
    # Test that JSON schemas don't describe plain JSON values (except at the top level), especially lists and dicts.
    # In other words, test that PLAIN_SCHEMAS is being used correctly and successfully.
    class Model(BaseModel):
        values: list[int]

    @dataclass
    class Dataclass:
        values: dict[str, int]

    @pydantic_dataclass
    class PydanticDataclass:
        values: list[dict[str, int]]

    logfire.info(
        'hi',
        list_of_lists=[[1, 2], [3, 4]],
        list_of_dicts=[{'a': 1}, {'b': 2}],
        dict_of_lists={'a': [1, 2], 'b': [3, 4]},
        dict_of_dicts={'a': {'a': 1}, 'b': {'b': 2}},
        complex_list=[1, 2, {'a': {'b': {'c': ['d']}}}, {'b': [2]}, True, False, None, 'a', 'b', [1, 2]],
        complex_dict={'a': 1, 'b': {'c': {'d': [1, 2]}}},
        list_of_objects=[
            Model(values=[1, 2]),
            Dataclass(values={'a': 1, 'b': 2}),
            PydanticDataclass(values=[{'a': 1, 'b': 2}, {'c': 3, 'd': 4}]),
        ],
    )

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'code.filepath': 'test_json_args.py',
                    'code.function': 'test_log_dicts_and_lists',
                    'code.lineno': 123,
                    'list_of_lists': '[[1,2],[3,4]]',
                    'list_of_dicts': '[{"a":1},{"b":2}]',
                    'dict_of_lists': '{"a":[1,2],"b":[3,4]}',
                    'dict_of_dicts': '{"a":{"a":1},"b":{"b":2}}',
                    'complex_list': '[1,2,{"a":{"b":{"c":["d"]}}},{"b":[2]},true,false,null,"a","b",[1,2]]',
                    'complex_dict': '{"a":1,"b":{"c":{"d":[1,2]}}}',
                    'list_of_objects': '[{"values":[1,2]},{"values":{"a":1,"b":2}},{"values":[{"a":1,"b":2},{"c":3,"d":4}]}]',
                    'logfire.json_schema': IsJson(
                        {
                            'type': 'object',
                            'properties': {
                                'list_of_lists': {'type': 'array'},
                                'list_of_dicts': {'type': 'array'},
                                'dict_of_lists': {'type': 'object'},
                                'dict_of_dicts': {'type': 'object'},
                                'complex_list': {'type': 'array'},
                                'complex_dict': {'type': 'object'},
                                'list_of_objects': {
                                    'type': 'array',
                                    'prefixItems': [
                                        {'type': 'object', 'title': 'Model', 'x-python-datatype': 'PydanticModel'},
                                        {'type': 'object', 'title': 'Dataclass', 'x-python-datatype': 'dataclass'},
                                        {
                                            'type': 'object',
                                            'title': 'PydanticDataclass',
                                            'x-python-datatype': 'dataclass',
                                        },
                                    ],
                                },
                            },
                        }
                    ),
                },
            }
        ]
    )


def test_recursive_objects(exporter: TestExporter) -> None:
    class Model(BaseModel):
        lst: list[Any]

    @dataclass
    class Dataclass:
        dct: dict[str, Any]

    dct: dict[str, Any] = {}
    data = Dataclass(dct=dct)
    lst = [data]
    model = Model(lst=lst)
    dct['model'] = model

    logfire.info(
        'hi',
        dct=dct,
        data=data,
        lst=lst,
        model=model,
    )

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'code.filepath': 'test_json_args.py',
                    'code.function': 'test_recursive_objects',
                    'code.lineno': 123,
                    'dct': IsJson(
                        # The reason this doesn't see a circular reference sooner
                        # is that BaseModel.model_dump() returns copies of the objects.
                        {'model': {'lst': [{'dct': {'model': {'lst': [{'dct': {'model': '<circular reference>'}}]}}}]}}
                    ),
                    'data': IsJson(
                        {'dct': {'model': {'lst': [{'dct': {'model': {'lst': ['<circular reference>']}}}]}}}
                    ),
                    'lst': IsJson(
                        [{'dct': {'model': {'lst': [{'dct': {'model': {'lst': ['<circular reference>']}}}]}}}]
                    ),
                    'model': IsJson(
                        {'lst': [{'dct': {'model': {'lst': [{'dct': {'model': '<circular reference>'}}]}}}]}
                    ),
                    'logfire.json_schema': IsJson(
                        {
                            'type': 'object',
                            'properties': {
                                'dct': {
                                    'type': 'object',
                                    'properties': {
                                        'model': {
                                            'type': 'object',
                                            'title': 'Model',
                                            'x-python-datatype': 'PydanticModel',
                                            'properties': {
                                                'lst': {
                                                    'type': 'array',
                                                    'items': {
                                                        'type': 'object',
                                                        'title': 'Dataclass',
                                                        'x-python-datatype': 'dataclass',
                                                    },
                                                }
                                            },
                                        }
                                    },
                                },
                                'data': {
                                    'type': 'object',
                                    'title': 'Dataclass',
                                    'x-python-datatype': 'dataclass',
                                    'properties': {
                                        'dct': {
                                            'type': 'object',
                                            'properties': {
                                                'model': {
                                                    'type': 'object',
                                                    'title': 'Model',
                                                    'x-python-datatype': 'PydanticModel',
                                                }
                                            },
                                        }
                                    },
                                },
                                'lst': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'title': 'Dataclass',
                                        'x-python-datatype': 'dataclass',
                                        'properties': {
                                            'dct': {
                                                'type': 'object',
                                                'properties': {
                                                    'model': {
                                                        'type': 'object',
                                                        'title': 'Model',
                                                        'x-python-datatype': 'PydanticModel',
                                                    }
                                                },
                                            }
                                        },
                                    },
                                },
                                'model': {
                                    'type': 'object',
                                    'title': 'Model',
                                    'x-python-datatype': 'PydanticModel',
                                    'properties': {
                                        'lst': {
                                            'type': 'array',
                                            'items': {
                                                'type': 'object',
                                                'title': 'Dataclass',
                                                'x-python-datatype': 'dataclass',
                                            },
                                        }
                                    },
                                },
                            },
                        }
                    ),
                },
            }
        ]
    )


def test_repeated_objects(exporter: TestExporter) -> None:
    @dataclass
    class Model:
        x: Any

    x = Model(x=1)
    m = Model(x=[x, x])

    logfire.info('hi', m=m)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'code.filepath': 'test_json_args.py',
                    'code.function': 'test_repeated_objects',
                    'code.lineno': 123,
                    'm': '{"x":[{"x":1},{"x":1}]}',
                    'logfire.json_schema': '{"type":"object","properties":{"m":{"type":"object","title":"Model","x-python-datatype":"dataclass","properties":{"x":{"type":"array","items":{"type":"object","title":"Model","x-python-datatype":"dataclass"}}}}}}',
                },
            }
        ]
    )


def test_numpy_array_truncation(exporter: TestExporter):
    logfire.info('hi', m=numpy.arange(13 * 3 * 11).reshape(13, 3, 11))

    truncated = [
        [
            [0, 1, 2, 3, 4, 6, 7, 8, 9, 10],
            [11, 12, 13, 14, 15, 17, 18, 19, 20, 21],
            [22, 23, 24, 25, 26, 28, 29, 30, 31, 32],
        ],
        [
            [33, 34, 35, 36, 37, 39, 40, 41, 42, 43],
            [44, 45, 46, 47, 48, 50, 51, 52, 53, 54],
            [55, 56, 57, 58, 59, 61, 62, 63, 64, 65],
        ],
        [
            [66, 67, 68, 69, 70, 72, 73, 74, 75, 76],
            [77, 78, 79, 80, 81, 83, 84, 85, 86, 87],
            [88, 89, 90, 91, 92, 94, 95, 96, 97, 98],
        ],
        [
            [99, 100, 101, 102, 103, 105, 106, 107, 108, 109],
            [110, 111, 112, 113, 114, 116, 117, 118, 119, 120],
            [121, 122, 123, 124, 125, 127, 128, 129, 130, 131],
        ],
        [
            [132, 133, 134, 135, 136, 138, 139, 140, 141, 142],
            [143, 144, 145, 146, 147, 149, 150, 151, 152, 153],
            [154, 155, 156, 157, 158, 160, 161, 162, 163, 164],
        ],
        [
            [264, 265, 266, 267, 268, 270, 271, 272, 273, 274],
            [275, 276, 277, 278, 279, 281, 282, 283, 284, 285],
            [286, 287, 288, 289, 290, 292, 293, 294, 295, 296],
        ],
        [
            [297, 298, 299, 300, 301, 303, 304, 305, 306, 307],
            [308, 309, 310, 311, 312, 314, 315, 316, 317, 318],
            [319, 320, 321, 322, 323, 325, 326, 327, 328, 329],
        ],
        [
            [330, 331, 332, 333, 334, 336, 337, 338, 339, 340],
            [341, 342, 343, 344, 345, 347, 348, 349, 350, 351],
            [352, 353, 354, 355, 356, 358, 359, 360, 361, 362],
        ],
        [
            [363, 364, 365, 366, 367, 369, 370, 371, 372, 373],
            [374, 375, 376, 377, 378, 380, 381, 382, 383, 384],
            [385, 386, 387, 388, 389, 391, 392, 393, 394, 395],
        ],
        [
            [396, 397, 398, 399, 400, 402, 403, 404, 405, 406],
            [407, 408, 409, 410, 411, 413, 414, 415, 416, 417],
            [418, 419, 420, 421, 422, 424, 425, 426, 427, 428],
        ],
    ]
    assert numpy.array(truncated).shape == (10, 3, 10)
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'code.filepath': 'test_json_args.py',
                    'code.function': 'test_numpy_array_truncation',
                    'code.lineno': 123,
                    'm': IsJson(truncated),
                    'logfire.json_schema': '{"type":"object","properties":{"m":{"type":"array","x-python-datatype":"ndarray","x-shape":[13,3,11],"x-dtype":"int64"}}}',
                },
            }
        ]
    )


def test_bad_getattr(exporter: TestExporter, caplog: pytest.LogCaptureFixture):
    class A:
        def __getattr__(self, item: str):
            raise RuntimeError

        def __repr__(self):
            return 'A()'

    logfire.info('hello', a=A())

    assert not caplog.messages
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'hello',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hello',
                    'logfire.msg': 'hello',
                    'code.filepath': 'test_json_args.py',
                    'code.function': 'test_bad_getattr',
                    'code.lineno': 123,
                    'a': '"A()"',
                    'logfire.json_schema': '{"type":"object","properties":{"a":{"type":"object","x-python-datatype":"unknown"}}}',
                },
            }
        ]
    )


def test_to_dict(exporter: TestExporter):
    class Foo:
        def to_dict(self):
            return {'x': 1}

    logfire.info('hi', foo=Foo())

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'code.filepath': 'test_json_args.py',
                    'code.function': 'test_to_dict',
                    'code.lineno': 123,
                    'foo': '{"x":1}',
                    'logfire.json_schema': '{"type":"object","properties":{"foo":{"type":"object","x-python-datatype":"unknown"}}}',
                },
            }
        ]
    )


def test_mock(exporter: TestExporter):
    class Mixin:
        def __repr__(self):
            return f'{self.__class__.__name__}()'

    class Foo(Mixin, Mock):
        pass

    class Bar(Mixin, MagicMock):
        pass

    logfire.info('hi', foo=Foo(), bar=Bar(), mock=Mock(), magic_mock=MagicMock())

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'code.filepath': 'test_json_args.py',
                    'code.function': 'test_mock',
                    'code.lineno': 123,
                    'foo': '"Foo()"',
                    'bar': '"Bar()"',
                    'mock': IsStr(regex=r'^"<Mock id=\'\d+\'>"'),
                    'magic_mock': IsStr(regex=r'^"<MagicMock id=\'\d+\'>"'),
                    'logfire.json_schema': '{"type":"object","properties":{"foo":{"type":"object","x-python-datatype":"unknown"},"bar":{"type":"object","x-python-datatype":"unknown"},"mock":{"type":"object","x-python-datatype":"unknown"},"magic_mock":{"type":"object","x-python-datatype":"unknown"}}}',
                },
            }
        ]
    )
