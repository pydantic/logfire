from __future__ import annotations

import json
import re
import sys
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import UUID

import numpy
import pandas
import pytest
from attrs import define
from pydantic import AnyUrl, BaseModel, ConfigDict, FilePath, NameEmail, SecretBytes, SecretStr
from pydantic.dataclasses import dataclass as pydantic_dataclass
from sqlalchemy import String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

import logfire
from logfire.testing import TestExporter

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:

    class StrEnum(str, Enum):
        ...


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


class Generator:
    def __repr__(self) -> str:
        return 'Generator()'

    def __iter__(self) -> Iterator[int]:
        yield from range(3)


def generator() -> Iterator[int]:
    yield from range(3)


gen = generator()


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


@define
class AttrsType:
    x: int
    y: int
    z: AttrsType | None = None


@pytest.mark.parametrize(
    'value,value_repr,value_json,json_schema',
    [
        pytest.param(
            ['a', 1, True],
            "['a', 1, True]",
            '["a",1,true]',
            {'type': 'array', 'x-python-datatype': 'list'},
            id='list',
        ),
        pytest.param(
            [],
            '[]',
            '[]',
            {'type': 'array', 'x-python-datatype': 'list'},
            id='empty_list',
        ),
        pytest.param(
            [MyDataclass(10), MyDataclass(20), MyDataclass(30)],
            '[MyDataclass(t=10), MyDataclass(t=20), MyDataclass(t=30)]',
            '[{"t":10},{"t":20},{"t":30}]',
            {
                'type': 'array',
                'x-python-datatype': 'list',
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
                'x-python-datatype': 'list',
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
            {'type': 'string', 'format': 'decimal'},
            id='decimal',
        ),
        pytest.param(
            date(2023, 1, 1),
            '2023-01-01',
            '"2023-01-01"',
            {'type': 'string', 'format': 'date'},
            id='date',
        ),
        pytest.param(
            datetime(2023, 1, 1, 10, 10),
            '2023-01-01 10:10:00',
            '"2023-01-01T10:10:00"',
            {'type': 'string', 'format': 'date-time'},
            id='datetime',
        ),
        pytest.param(
            time(12, 10),
            '12:10:00',
            '"12:10:00"',
            {'type': 'string', 'format': 'time'},
            id='time',
        ),
        pytest.param(
            timedelta(1, seconds=3672),
            '1 day, 1:01:12',
            '"90072.0"',
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
                'x-python-datatype': 'enum',
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
                        'x-python-datatype': 'enum',
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
                'x-python-datatype': 'enum',
                'enum': [1, 'str', {'t': 1}],
            },
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
            FilePath(__file__),
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
            MyModel(x='x', y=10, u='http://test.com'),
            "x='x' y=10 u=Url('http://test.com/')",
            '{"x":"x","y":10,"u":"http://test.com/"}',
            {
                'type': 'object',
                'title': 'MyModel',
                'x-python-datatype': 'PydanticModel',
                'properties': {'u': {'type': 'string', 'format': 'uri'}},
            },
            id='pydantic_model',
        ),
        pytest.param(
            MyModel.model_validate(dict(x='x', y=10, u='http://test.com', extra_key=MyDataclass(10))),
            "x='x' y=10 u=Url('http://test.com/')",
            '{"x":"x","y":10,"u":"http://test.com/","extra_key":{"t":10}}',
            {
                'type': 'object',
                'title': 'MyModel',
                'x-python-datatype': 'PydanticModel',
                'properties': {
                    'u': {'type': 'string', 'format': 'uri'},
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
            {'type': 'object', 'title': 'MyPydanticDataclass', 'x-python-datatype': 'pydantic-dataclass'},
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
                'x-python-datatype': 'pydantic-dataclass',
                'properties': {
                    't': {
                        'type': 'object',
                        'title': 'MyPydanticDataclass',
                        'x-python-datatype': 'pydantic-dataclass',
                    }
                },
            },
            id='pydantic_complex_dataclass',
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
            {'type': 'object', 'title': 'Generator', 'x-python-datatype': 'unknown'},
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
            {'type': 'object', 'title': 'MyArbitraryType', 'x-python-datatype': 'unknown'},
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
                'x-indexes': [0, 1],
            },
            id='dataframe',
        ),
        pytest.param(
            pandas.DataFrame(
                data={f'col{i}': [i * j for j in range(1, 23)] for i in range(1, 13)},
                index=[f'i{x}' for x in range(1, 23)],
            ),
            '     col1  col2  col3  col4  col5  ...  col8  col9  col10  col11  col12\n',
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
                'x-indexes': [
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
            ' [  2   4   6   8  10  12  14  16  18  20  22  24]\n'
            ' [  3   6   9  12  15  18  21  24  27  30  33  36]\n'
            ' [  4   8  12  16  20  24  28  32  36  40  44  48]\n'
            ' [  5  10  15  20  25  30  35  40  45  50  55  60]\n'
            ' [  6  12  18  24  30  36  42  48  54  60  66  72]\n'
            ' [  7  14  21  28  35  42  49  56  63  70  77  84]\n'
            ' [  8  16  24  32  40  48  56  64  72  80  88  96]\n'
            ' [  9  18  27  36  45  54  63  72  81  90  99 108]\n'
            ' [ 10  20  30  40  50  60  70  80  90 100 110 120]\n'
            ' [ 11  22  33  44  55  66  77  88  99 110 121 132]\n'
            ' [ 12  24  36  48  60  72  84  96 108 120 132 144]\n'
            ' [ 13  26  39  52  65  78  91 104 117 130 143 156]\n'
            ' [ 14  28  42  56  70  84  98 112 126 140 154 168]\n'
            ' [ 15  30  45  60  75  90 105 120 135 150 165 180]\n'
            ' [ 16  32  48  64  80  96 112 128 144 160 176 192]\n'
            ' [ 17  34  51  68  85 102 119 136 153 170 187 204]\n'
            ' [ 18  36  54  72  90 108 126 144 162 180 198 216]\n'
            ' [ 19  38  57  76  95 114 133 152 171 190 209 228]\n'
            ' [ 20  40  60  80 100 120 140 160 180 200 220 240]\n'
            ' [ 21  42  63  84 105 126 147 168 189 210 231 252]\n'
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
            '  [   2    4    6 ...   20   22   24]\n'
            '  [   3    6    9 ...   30   33   36]\n'
            '  ...\n'
            '  [  10   20   30 ...  100  110  120]\n'
            '  [  11   22   33 ...  110  121  132]\n'
            '  [  12   24   36 ...  120  132  144]]\n'
            '\n'
            ' [[   2    4    6 ...   20   22   24]\n'
            '  [   4    8   12 ...   40   44   48]\n'
            '  [   6   12   18 ...   60   66   72]\n'
            '  ...\n'
            '  [  20   40   60 ...  200  220  240]\n'
            '  [  22   44   66 ...  220  242  264]\n'
            '  [  24   48   72 ...  240  264  288]]\n'
            '\n'
            ' [[   3    6    9 ...   30   33   36]\n'
            '  [   6   12   18 ...   60   66   72]\n'
            '  [   9   18   27 ...   90   99  108]\n'
            '  ...\n'
            '  [  30   60   90 ...  300  330  360]\n'
            '  [  33   66   99 ...  330  363  396]\n'
            '  [  36   72  108 ...  360  396  432]]\n'
            '\n'
            ' ...\n'
            '\n'
            ' [[  10   20   30 ...  100  110  120]\n'
            '  [  20   40   60 ...  200  220  240]\n'
            '  [  30   60   90 ...  300  330  360]\n'
            '  ...\n'
            '  [ 100  200  300 ... 1000 1100 1200]\n'
            '  [ 110  220  330 ... 1100 1210 1320]\n'
            '  [ 120  240  360 ... 1200 1320 1440]]\n'
            '\n'
            ' [[  11   22   33 ...  110  121  132]\n'
            '  [  22   44   66 ...  220  242  264]\n'
            '  [  33   66   99 ...  330  363  396]\n'
            '  ...\n'
            '  [ 110  220  330 ... 1100 1210 1320]\n'
            '  [ 121  242  363 ... 1210 1331 1452]\n'
            '  [ 132  264  396 ... 1320 1452 1584]]\n'
            '\n'
            ' [[  12   24   36 ...  120  132  144]\n'
            '  [  24   48   72 ...  240  264  288]\n'
            '  [  36   72  108 ...  360  396  432]\n'
            '  ...\n'
            '  [ 120  240  360 ... 1200 1320 1440]\n'
            '  [ 132  264  396 ... 1320 1452 1584]\n'
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
            id='attrs',
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

    assert s.name.startswith(f'test message var={value_repr}'), s.name
    assert s.attributes['var__JSON'] == value_json
    assert json.loads(s.attributes['logfire.json_schema'])['properties']['var'] == json_schema


def test_log_sqlalchemy_class(exporter: TestExporter) -> None:
    class Base(DeclarativeBase):
        pass

    class Model(Base):
        __tablename__ = 'model'

        id: Mapped[int] = mapped_column('user_id', primary_key=True)
        name: Mapped[str] = mapped_column('user_name', String(30))

        def __init__(self, id, name):
            self.id = id
            self.name = name

    engine = create_engine('sqlite:///:memory:')
    session = Session(engine)
    Model.metadata.create_all(engine)
    model = Model(1, 'test name')
    session.add(model)
    session.commit()

    var = session.query(Model).all()[0]
    logfire.info('test message {var=}', var=var)

    s = exporter.exported_spans[0]

    assert s.name.startswith(
        'test message var=<tests.test_json_args.test_log_sqlalchemy_class.<locals>.Model object at'
    )
    assert s.attributes['var__JSON'] == '{"id":1,"name":"test name"}'
    # insert_assert(s.attributes['logfire.json_schema'])
    assert (
        s.attributes['logfire.json_schema']
        == '{"type":"object","properties":{"var":{"type":"object","title":"Model","x-python-datatype":"sqlalchemy"}}}'
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

    # insert_assert(exporter.exported_spans_as_dict(_include_pending_spans=True)[0]['attributes'])
    assert exporter.exported_spans_as_dict(_include_pending_spans=True)[0]['attributes'] == {
        'logfire.span_type': 'log',
        'logfire.level_name': 'info',
        'logfire.level_num': 9,
        'logfire.msg_template': 'test message {a=} {complex_list=} {complex_dict=}',
        'logfire.msg': "test message a=1 complex_list=['a', 1, MyModel(x='x', y=datetime.datetime(2023, 1, 1, 0, 0)), test_log_non_scalar_complex_args.<locals>.MyDataclass(t=10), test_log_non_scalar_complex_args.<locals>.MyPydanticDataclass(p=20)] complex_dict={'k1': 'v1', 'model': MyModel(x='x', y=datetime.datetime(2023, 1, 1, 0, 0)), 'dataclass': test_log_non_scalar_complex_args.<locals>.MyDataclass(t=10), 'pydantic_dataclass': test_log_non_scalar_complex_args.<locals>.MyPydanticDataclass(p=20)}",
        'logfire.json_schema': '{"type":"object","properties":{"a":{},"complex_list":{"type":"array","x-python-datatype":"list","prefixItems":[{},{},{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel","properties":{"y":{"type":"string","format":"date-time"}}},{"type":"object","title":"MyDataclass","x-python-datatype":"dataclass"},{"type":"object","title":"MyPydanticDataclass","x-python-datatype":"pydantic-dataclass"}]},"complex_dict":{"type":"object","properties":{"model":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel","properties":{"y":{"type":"string","format":"date-time"}}},"dataclass":{"type":"object","title":"MyDataclass","x-python-datatype":"dataclass"},"pydantic_dataclass":{"type":"object","title":"MyPydanticDataclass","x-python-datatype":"pydantic-dataclass"}}}}}',
        'code.filepath': 'test_json_args.py',
        'code.lineno': 123,
        'code.function': 'test_log_non_scalar_complex_args',
        'a': 1,
        'complex_list__JSON': '["a",1,{"x":"x","y":"2023-01-01T00:00:00"},{"t":10},{"p":20}]',
        'complex_dict__JSON': '{"k1":"v1","model":{"x":"x","y":"2023-01-01T00:00:00"},"dataclass":{"t":10},"pydantic_dataclass":{"p":20}}',
    }
