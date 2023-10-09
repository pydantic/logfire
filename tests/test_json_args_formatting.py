from typing import Any

import pytest

from logfire.json_encoder import DataType
from logfire.json_formatter import json_args_value_formatter, json_args_value_formatter_compact


@pytest.mark.parametrize(
    'value,formatted_value',
    [
        (
            ['a', 1, True],
            """[
    'a',
    1,
    True,
]""",
        ),
        (
            {'k1': 'v1', 'k2': 2},
            """{
    'k1': 'v1',
    'k2': 2,
}""",
        ),
        ({'$__datatype__': 'bytes-utf8', 'data': 'test bytes'}, "b'test bytes'"),
        ({'$__datatype__': 'bytes-base64', 'data': 'gQ=='}, "b'\\x81'"),
        (
            {'$__datatype__': 'tuple', 'data': [1, 2, 'b']},
            """(
    1,
    2,
    'b',
)""",
        ),
        (
            {'$__datatype__': 'tuple', 'data': []},
            '()',
        ),
        (
            {'$__datatype__': 'set', 'data': ['s', 1, True]},
            """{
    's',
    1,
    True,
}""",
        ),
        (
            {'$__datatype__': 'frozenset', 'data': ['s', 1, True]},
            """frozenset({
    's',
    1,
    True,
})""",
        ),
        ({'$__datatype__': 'Decimal', 'data': '1.7'}, "Decimal('1.7')"),
        ({'$__datatype__': 'date', 'data': '2023-01-01'}, "date('2023-01-01')"),
        ({'$__datatype__': 'datetime', 'data': '2023-01-01T10:10:00'}, "datetime('2023-01-01T10:10:00')"),
        ({'$__datatype__': 'time', 'data': '12:10:00'}, "time('12:10:00')"),
        ({'$__datatype__': 'timedelta', 'data': 90072.0}, 'datetime.timedelta(days=1, seconds=3672)'),
        ({'$__datatype__': 'Enum', 'data': 3, 'cls': 'Color'}, 'Color(3)'),
        (
            {'$__datatype__': 'deque', 'data': [4, 5]},
            """deque([
    4,
    5,
])""",
        ),
        ({'$__datatype__': 'IPv4Address', 'data': '127.0.0.1'}, "IPv4Address('127.0.0.1')"),
        ({'$__datatype__': 'IPv4Interface', 'data': '192.0.2.5/24'}, "IPv4Interface('192.0.2.5/24')"),
        ({'$__datatype__': 'IPv4Network', 'data': '192.0.2.0/24'}, "IPv4Network('192.0.2.0/24')"),
        ({'$__datatype__': 'IPv6Address', 'data': '2001:db8::1000'}, "IPv6Address('2001:db8::1000')"),
        ({'$__datatype__': 'IPv6Interface', 'data': '2001:db8::1000/128'}, "IPv6Interface('2001:db8::1000/128')"),
        ({'$__datatype__': 'IPv6Network', 'data': '2001:db8::1000/128'}, "IPv6Network('2001:db8::1000/128')"),
        ({'$__datatype__': 'NameEmail', 'data': 'John Doe <john.doe@mail.com>'}, 'John Doe <john.doe@mail.com>'),
        ({'$__datatype__': 'PosixPath', 'data': '/tmp/test.py'}, "PosixPath('/tmp/test.py')"),
        ({'$__datatype__': 'Pattern', 'data': 'test'}, "re.compile('test')"),
        ({'$__datatype__': 'SecretBytes', 'data': "b\'**********\'"}, "SecretBytes(b'**********')"),
        ({'$__datatype__': 'SecretStr', 'data': '**********'}, "SecretStr('**********')"),
        (
            {'$__datatype__': 'UUID', 'data': '7265bc22-ccb0-4ee2-97f0-5dd206f01ae4', 'version': 4},
            "UUID('7265bc22-ccb0-4ee2-97f0-5dd206f01ae4')",
        ),
        (
            {
                '$__datatype__': 'BaseModel',
                'data': {'x': 'x', 'y': 10, 'u': {'$__datatype__': 'Url', 'data': 'http://test.com/'}},
                'cls': 'MyModel',
            },
            """MyModel(
    x='x',
    y=10,
    u=Url('http://test.com/'),
)""",
        ),
        (
            {'$__datatype__': 'dataclass', 'data': {'t': 10}, 'cls': 'MyDataclass'},
            """MyDataclass(
    t=10,
)""",
        ),
        (
            {'$__datatype__': 'dataclass', 'data': {}, 'cls': 'MyDataclass'},
            'MyDataclass()',
        ),
        (
            {'$__datatype__': 'BaseModel', 'data': {'p': 20}, 'cls': 'MyPydanticDataclass'},
            """MyPydanticDataclass(
    p=20,
)""",
        ),
        (
            {'$__datatype__': 'Exception', 'data': 'Test value error', 'cls': 'ValueError'},
            "ValueError('Test value error')",
        ),
        (
            {'$__datatype__': 'Mapping', 'data': {'foo': 'bar'}, 'cls': 'MyMapping'},
            """MyMapping({
    'foo': 'bar',
})""",
        ),
        ({'$__datatype__': 'Sequence', 'data': [0, 1, 2, 3], 'cls': 'range'}, 'range(0, 4)'),
        (
            {'$__datatype__': 'Sequence', 'data': [1, 2, 3], 'cls': 'MySequence'},
            """MySequence([
    1,
    2,
    3,
])""",
        ),
        (
            {'$__datatype__': 'MyArbitaryType', 'data': 'MyArbitaryType(12)', 'cls': 'MyArbitaryType'},
            'MyArbitaryType(12)',
        ),
        ({'$__datatype__': 'unknown', 'data': '<this is repr>'}, '<this is repr>'),
    ],
    ids=repr,
)
def test_json_args_value_formatting(value: Any, formatted_value: str):
    assert json_args_value_formatter(value) == formatted_value


def test_nested_json_args_value_formatting():
    value = [
        'a',
        1,
        {
            '$__datatype__': 'BaseModel',
            'data': {'x': 'x', 'y': {'$__datatype__': 'datetime', 'data': '2023-01-01T00:00:00'}},
            'cls': 'MyModel',
        },
        {'$__datatype__': 'dataclass', 'data': {'t': 10}, 'cls': 'MyDataclass'},
        {'$__datatype__': 'BaseModel', 'data': {'p': 20}, 'cls': 'MyPydanticDataclass'},
    ]

    assert (
        json_args_value_formatter(value)
        == """[
    'a',
    1,
    MyModel(
        x='x',
        y=datetime('2023-01-01T00:00:00'),
    ),
    MyDataclass(
        t=10,
    ),
    MyPydanticDataclass(
        p=20,
    ),
]"""
    )


@pytest.mark.parametrize(
    'value,formatted_value',
    [
        (['a', 1, True], "['a', 1, True]"),
        ({'k1': 'v1', 'k2': 2}, "{'k1': 'v1', 'k2': 2}"),
        ({'$__datatype__': 'tuple', 'data': [1, 2, 'b']}, "(1, 2, 'b')"),
        ({'$__datatype__': 'tuple', 'data': []}, '()'),
        ({'$__datatype__': 'set', 'data': ['s', 1, True]}, "{'s', 1, True}"),
        ({'$__datatype__': 'frozenset', 'data': ['s', 1, True]}, "frozenset({'s', 1, True})"),
        ({'$__datatype__': 'Decimal', 'data': '1.7'}, "Decimal('1.7')"),
        ({'$__datatype__': 'date', 'data': '2023-01-01'}, "date('2023-01-01')"),
        ({'$__datatype__': 'datetime', 'data': '2023-01-01T10:10:00'}, "datetime('2023-01-01T10:10:00')"),
        ({'$__datatype__': 'time', 'data': '12:10:00'}, "time('12:10:00')"),
        ({'$__datatype__': 'timedelta', 'data': 90072.0}, 'datetime.timedelta(days=1, seconds=3672)'),
        ({'$__datatype__': 'Enum', 'data': 3, 'cls': 'Color'}, 'Color(3)'),
        ({'$__datatype__': 'deque', 'data': [4, 5]}, 'deque([4, 5])'),
        (
            {'$__datatype__': 'UUID', 'data': '7265bc22-ccb0-4ee2-97f0-5dd206f01ae4', 'version': 4},
            "UUID('7265bc22-ccb0-4ee2-97f0-5dd206f01ae4')",
        ),
        (
            {
                '$__datatype__': 'BaseModel',
                'data': {'x': 'x', 'y': 10, 'u': {'$__datatype__': 'Url', 'data': 'http://test.com/'}},
                'cls': 'MyModel',
            },
            "MyModel(x='x', y=10, u=Url('http://test.com/'))",
        ),
        ({'$__datatype__': 'dataclass', 'data': {'t': 10}, 'cls': 'MyDataclass'}, 'MyDataclass(t=10)'),
        ({'$__datatype__': 'dataclass', 'data': {}, 'cls': 'MyDataclass'}, 'MyDataclass()'),
        ({'$__datatype__': 'dataclass', 'data': {'p': 20}, 'cls': 'MyPydanticDataclass'}, 'MyPydanticDataclass(p=20)'),
        (
            {'$__datatype__': 'Exception', 'data': 'Test value error', 'cls': 'ValueError'},
            "ValueError('Test value error')",
        ),
        ({'$__datatype__': 'Mapping', 'data': {'foo': 'bar'}, 'cls': 'MyMapping'}, "MyMapping({'foo': 'bar'})"),
        ({'$__datatype__': 'Sequence', 'data': [0, 1, 2, 3], 'cls': 'range'}, 'range(0, 4)'),
        ({'$__datatype__': 'Sequence', 'data': [1, 2, 3], 'cls': 'MySequence'}, 'MySequence([1, 2, 3])'),
        (
            {'$__datatype__': 'MyArbitaryType', 'data': 'MyArbitaryType(12)', 'cls': 'MyArbitaryType'},
            'MyArbitaryType(12)',
        ),
        ({'$__datatype__': 'unknown', 'data': '<this is repr>'}, '<this is repr>'),
        ({'$__datatype__': 'generator', 'data': [0, 1, 2]}, 'generator((0, 1, 2))'),
    ],
)
def test_json_args_value_formatting_compact(value: Any, formatted_value: str):
    assert json_args_value_formatter_compact(value) == formatted_value


def test_all_types_covered():
    assert set(DataType.__args__) == set(json_args_value_formatter_compact._data_type_map.keys())
