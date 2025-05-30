from typing import Any, cast

import pytest

from logfire._internal.json_formatter import json_args_value_formatter, json_args_value_formatter_compact
from logfire._internal.json_types import ArraySchema, DataType, JSONSchema


@pytest.mark.parametrize(
    'value,schema,formatted_value',
    [
        pytest.param(
            ['a', 1, True],
            {'type': 'array'},
            """[
    'a',
    1,
    True,
]""",
            id='list',
        ),
        pytest.param(
            ['a', 1, 'MyArbitraryType(12)', {'k1': 'v1', 'k2': 2}],
            {
                'type': 'array',
                'prefixItems': [
                    {},
                    {},
                    {'type': 'object', 'x-python-datatype': 'unknown'},
                    {'type': 'object'},
                ],
            },
            """[
    'a',
    1,
    MyArbitraryType(12),
    {
        'k1': 'v1',
        'k2': 2,
    },
]""",
            id='complex_list',
        ),
        pytest.param(
            [[1, 2, 3], [4, 5, 6]],
            {'type': 'array', 'items': {'type': 'array'}},
            """[
    [
        1,
        2,
        3,
    ],
    [
        4,
        5,
        6,
    ],
]""",
            id='list_of_lists',
        ),
        pytest.param(
            {'k1': 'v1', 'k2': 2},
            {'type': 'object', 'properties': {'k1': {}, 'k2': {}}},
            """{
    'k1': 'v1',
    'k2': 2,
}""",
            id='dict',
        ),
        pytest.param(
            {'MyDataclass(t=10)': 'v1', 'MyDataclass(t=20)': 2},
            {'type': 'object'},
            """{
    'MyDataclass(t=10)': 'v1',
    'MyDataclass(t=20)': 2,
}""",
            id='dict_with_dataclass_key',
        ),
        pytest.param(
            {'Potato()': 1, 'Banana()': 2},
            {'type': 'object'},
            """{
    'Potato()': 1,
    'Banana()': 2,
}""",
            id='complex_key_types',
        ),
        pytest.param(
            '"test bytes"',
            {'type': 'string', 'x-python-datatype': 'bytes'},
            '"test bytes"',
            id='bytes_utf8',
        ),
        pytest.param(
            '"\\\\x81"',
            {'type': 'string', 'x-python-datatype': 'bytes'},
            '"\\\\x81"',
            id='bytes_base64',
        ),
        pytest.param(
            '"\\\\x81"',
            {'type': 'string', 'x-python-datatype': 'bytes', 'title': 'MyBytes'},
            'MyBytes("\\\\x81")',
            id='bytes_with_title',
        ),
        pytest.param(
            ['a', 1, True],
            {'type': 'array', 'x-python-datatype': 'tuple'},
            """(
    'a',
    1,
    True,
)""",
            id='tuple',
        ),
        pytest.param(
            [],
            {'type': 'array', 'x-python-datatype': 'tuple'},
            '()',
            id='empty_tuple',
        ),
        pytest.param(
            ['s', 1, True],
            {'type': 'array', 'x-python-datatype': 'set'},
            """{
    's',
    1,
    True,
}""",
            id='set',
        ),
        pytest.param(
            ['s', 1, True],
            {'type': 'array', 'x-python-datatype': 'frozenset'},
            """frozenset({
    's',
    1,
    True,
})""",
            id='frozenset',
        ),
        pytest.param(
            '1.7',
            {'type': 'string', 'x-python-datatype': 'Decimal'},
            "Decimal('1.7')",
            id='decimal',
        ),
        pytest.param(
            '2023-01-01',
            {'type': 'string', 'x-python-datatype': 'date'},
            'datetime.date(2023, 1, 1)',
            id='date',
        ),
        pytest.param(
            '2023-01-01T10:10:00',
            {'type': 'string', 'x-python-datatype': 'datetime'},
            'datetime.datetime(2023, 1, 1, 10, 10)',
            id='datetime',
        ),
        pytest.param(
            '12:10:00',
            {'type': 'string', 'x-python-datatype': 'time'},
            'datetime.time(12, 10)',
            id='time',
        ),
        pytest.param(
            90072.0,
            {'type': 'number', 'x-python-datatype': 'timedelta'},
            'datetime.timedelta(days=1, seconds=3672)',
            id='timedelta',
        ),
        pytest.param(
            3,
            {'type': 'integer', 'title': 'Color', 'x-python-datatype': 'Enum', 'enum': [1, 2, 3]},
            'Color(3)',
            id='enum',
        ),
        pytest.param(
            [4, 5],
            {'type': 'array', 'x-python-datatype': 'deque'},
            """deque([
    4,
    5,
])""",
            id='deque',
        ),
        pytest.param(
            '127.0.0.1',
            {'type': 'string', 'x-python-datatype': 'IPv4Address'},
            "IPv4Address('127.0.0.1')",
            id='IPv4Address',
        ),
        pytest.param(
            '192.0.2.5/24',
            {'type': 'string', 'x-python-datatype': 'IPv4Interface'},
            "IPv4Interface('192.0.2.5/24')",
            id='IPv4Interface',
        ),
        pytest.param(
            '192.0.2.0/24',
            {'type': 'string', 'x-python-datatype': 'IPv4Network'},
            "IPv4Network('192.0.2.0/24')",
            id='IPv4Network',
        ),
        pytest.param(
            '2001:db8::1000',
            {'type': 'string', 'x-python-datatype': 'IPv6Address'},
            "IPv6Address('2001:db8::1000')",
            id='IPv6Address',
        ),
        pytest.param(
            '2001:db8::1000/128',
            {'type': 'string', 'x-python-datatype': 'IPv6Interface'},
            "IPv6Interface('2001:db8::1000/128')",
            id='IPv6Interface',
        ),
        pytest.param(
            '2001:db8::1000/128',
            {'type': 'string', 'x-python-datatype': 'IPv6Network'},
            "IPv6Network('2001:db8::1000/128')",
            id='IPv6Network',
        ),
        pytest.param(
            'John Doe <john.doe@mail.com>',
            {'type': 'string', 'x-python-datatype': 'NameEmail'},
            'John Doe <john.doe@mail.com>',
            id='NameEmail',
        ),
        pytest.param(
            '/tmp/test.py',
            {'type': 'string', 'x-python-datatype': 'PosixPath'},
            "PosixPath('/tmp/test.py')",
            id='PosixPath',
        ),
        pytest.param(
            'test',
            {'type': 'string', 'x-python-datatype': 'Pattern'},
            "re.compile('test')",
            id='Pattern',
        ),
        pytest.param(
            "b'**********'",
            {'type': 'string', 'x-python-datatype': 'SecretBytes'},
            "SecretBytes(b'**********')",
            id='SecretBytes',
        ),
        pytest.param(
            '**********',
            {'type': 'string', 'x-python-datatype': 'SecretStr'},
            "SecretStr('**********')",
            id='SecretStr',
        ),
        pytest.param(
            '7265bc22-ccb0-4ee2-97f0-5dd206f01ae4',
            {'type': 'string', 'x-python-datatype': 'UUID'},
            "UUID('7265bc22-ccb0-4ee2-97f0-5dd206f01ae4')",
            id='UUID',
        ),
        pytest.param(
            {'x': 'x', 'y': 10, 'u': 'http://test.com/'},
            {
                'type': 'object',
                'x-python-datatype': 'PydanticModel',
                'title': 'MyModel',
                'properties': {'u': {'type': 'string', 'x-python-datatype': 'Url'}},
            },
            """MyModel(
    x='x',
    y=10,
    u=Url('http://test.com/'),
)""",
            id='pydantic_model',
        ),
        pytest.param(
            {'t': 10},
            {
                'type': 'object',
                'x-python-datatype': 'dataclass',
                'title': 'MyDataclass',
            },
            """MyDataclass(
    t=10,
)""",
            id='dataclass',
        ),
        pytest.param(
            {},
            {
                'type': 'object',
                'x-python-datatype': 'dataclass',
                'title': 'MyDataclass',
            },
            'MyDataclass()',
            id='empty_dataclass',
        ),
        pytest.param(
            {'p': 20},
            {
                'type': 'object',
                'x-python-datatype': 'dataclass',
                'title': 'MyPydanticDataclass',
            },
            """MyPydanticDataclass(
    p=20,
)""",
            id='pydantic_dataclass',
        ),
        pytest.param(
            'Test value error',
            {'type': 'string', 'x-python-datatype': 'Exception', 'title': 'ValueError'},
            "ValueError('Test value error')",
            id='Exception',
        ),
        pytest.param(
            {'foo': 'bar'},
            {'type': 'object', 'x-python-datatype': 'Mapping', 'title': 'MyMapping'},
            """MyMapping({
    'foo': 'bar',
})""",
            id='Mapping',
        ),
        pytest.param(
            [0, 1, 2, 3],
            {'type': 'array', 'x-python-datatype': 'Sequence', 'title': 'range'},
            'range(0, 4)',
            id='Sequence',
        ),
        pytest.param(
            [1, 2, 3],
            {'type': 'array', 'x-python-datatype': 'Sequence', 'title': 'MySequence'},
            """MySequence([
    1,
    2,
    3,
])""",
            id='CustomSequence',
        ),
        pytest.param(
            'MyArbitraryType(12)',
            {'type': 'string', 'x-python-datatype': 'unknown'},
            'MyArbitraryType(12)',
            id='arbitrary_type',
        ),
        pytest.param(
            '<this is repr>',
            {'type': 'string', 'x-python-datatype': 'unknown'},
            '<this is repr>',
            id='repr',
        ),
        pytest.param(
            [[1, 3], [2, 4]],
            {
                'type': 'array',
                'x-python-datatype': 'DataFrame',
                'x-columns': ['col1', 'col2'],
                'x-indices': ['0', '1'],
                'x-row-count': 2,
                'x-column-count': 2,
            },
            '  | col1 | col2\n--+------+-----\n0 | 1    | 3   \n1 | 2    | 4   \n\n[2 rows x 2 columns]',
            id='dataframe',
        ),
        pytest.param(
            [[1, 2, 4, 5], [2, 4, 8, 10], [4, 8, 16, 20], [5, 10, 20, 25]],
            {
                'type': 'array',
                'x-python-datatype': 'DataFrame',
                'x-columns': ['col1', 'col2', 'col4', 'col5'],
                'x-indices': ['a', 'b', 'd', 'e'],
                'x-row-count': 5,
                'x-column-count': 5,
            },
            '    | col1 | col2 | ... | col4 | col5\n'
            '----+------+------+-----+------+-----\n'
            'a   | 1    | 2    | ... | 4    | 5   \n'
            'b   | 2    | 4    | ... | 8    | 10  \n'
            '... | ...  | ...  | ... | ...  | ... \n'
            'd   | 4    | 8    | ... | 16   | 20  \n'
            'e   | 5    | 10   | ... | 20   | 25  \n\n'
            '[5 rows x 5 columns]',
            id='big_DataFrame',
        ),
        pytest.param(
            [['1', '2'], ['3', '4']],
            {'type': 'array', 'x-python-datatype': 'ndarray', 'x-shape': [2, 2], 'x-dtype': 'str'},
            """array([
    [
        '1',
        '2',
    ],
    [
        '3',
        '4',
    ],
])""",
            id='ndarray',
        ),
        pytest.param(
            [['1', '2', '4', '5'], ['2', '4', '8', '10'], ['4', '8', '16', '20'], ['5', '10', '20', '25']],
            {'type': 'array', 'x-python-datatype': 'ndarray', 'x-shape': [4, 4], 'x-dtype': 'str'},
            """array([
    [
        '1',
        '2',
        '4',
        '5',
    ],
    [
        '2',
        '4',
        '8',
        '10',
    ],
    [
        '4',
        '8',
        '16',
        '20',
    ],
    [
        '5',
        '10',
        '20',
        '25',
    ],
])""",
            id='big_ndarray',
        ),
        pytest.param(
            {'x': 1, 'y': 2},
            {'type': 'object', 'x-python-datatype': 'attrs', 'title': 'AttrsType'},
            'AttrsType(\n    x=1,\n    y=2,\n)',
            id='attrs',
        ),
        pytest.param(
            {'id': 1, 'name': 'test name'},
            {'type': 'object', 'x-python-datatype': 'sqlalchemy', 'title': 'Model'},
            "Model(\n    id=1,\n    name='test name',\n)",
            id='sqlalchemy',
        ),
    ],
    ids=repr,
)
def test_json_args_value_formatting(value: Any, schema: JSONSchema, formatted_value: str):
    assert json_args_value_formatter(value, schema=schema) == formatted_value


def test_nested_json_args_value_formatting():
    value = [
        'a',
        1,
        {'x': 'x', 'y': '2023-01-01T00:00:00'},
        # {
        #     '$__datatype__': 'BaseModel',
        #     'data': {'x': 'x', 'y': {'$__datatype__': 'datetime', 'data': '2023-01-01T00:00:00'}},
        #     'cls': 'MyModel',
        # },
        {'t': 10},
        # {'$__datatype__': 'dataclass', 'data': {'t': 10}, 'cls': 'MyDataclass'},
        {'p': 20},
        # {'$__datatype__': 'BaseModel', 'data': {'p': 20}, 'cls': 'MyPydanticDataclass'},
    ]
    schema = cast(
        ArraySchema,
        {
            'type': 'array',
            'prefixItems': [
                {},
                {},
                {
                    'type': 'object',
                    'x-python-datatype': 'PydanticModel',
                    'title': 'MyModel',
                    'properties': {'y': {'type': 'string', 'x-python-datatype': 'datetime'}},
                },
                {
                    'type': 'object',
                    'x-python-datatype': 'dataclass',
                    'title': 'MyDataclass',
                },
                {
                    'type': 'object',
                    'x-python-datatype': 'dataclass',
                    'title': 'MyPydanticDataclass',
                },
            ],
        },
    )

    assert (
        json_args_value_formatter(value, schema=schema)
        == """[
    'a',
    1,
    MyModel(
        x='x',
        y=datetime.datetime(2023, 1, 1, 0, 0),
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
    'value,schema,formatted_value',
    [
        pytest.param(
            ['a', 1, True],
            {'type': 'array'},
            "['a', 1, True]",
            id='list',
        ),
        pytest.param(
            {'k1': 'v1', 'k2': 2},
            {'type': 'object', 'properties': {'k1': {}, 'k2': {}}},
            "{'k1': 'v1', 'k2': 2}",
            id='dict',
        ),
        pytest.param(
            [1, 2, 'b'],
            {'type': 'array', 'x-python-datatype': 'tuple'},
            "(1, 2, 'b')",
            id='tuple',
        ),
        pytest.param(
            [],
            {'type': 'array', 'x-python-datatype': 'tuple'},
            '()',
            id='empty_tuple',
        ),
        pytest.param(
            ['s', 1, True],
            {'type': 'array', 'x-python-datatype': 'set'},
            "{'s', 1, True}",
            id='set',
        ),
        pytest.param(
            ['s', 1, True],
            {'type': 'array', 'x-python-datatype': 'frozenset'},
            "frozenset({'s', 1, True})",
            id='frozenset',
        ),
        pytest.param(
            '1.7',
            {'type': 'string', 'x-python-datatype': 'Decimal'},
            "Decimal('1.7')",
            id='decimal',
        ),
        pytest.param(
            '2023-01-01',
            {'type': 'string', 'x-python-datatype': 'date'},
            'datetime.date(2023, 1, 1)',
            id='date',
        ),
        pytest.param(
            '2023-01-01T10:10:00',
            {'type': 'string', 'x-python-datatype': 'datetime'},
            'datetime.datetime(2023, 1, 1, 10, 10)',
            id='datetime',
        ),
        pytest.param(
            '12:10:00',
            {'type': 'string', 'x-python-datatype': 'time'},
            'datetime.time(12, 10)',
            id='time',
        ),
        pytest.param(
            90072.0,
            {'type': 'number', 'x-python-datatype': 'timedelta'},
            'datetime.timedelta(days=1, seconds=3672)',
            id='timedelta',
        ),
        pytest.param(
            3,
            {'type': 'integer', 'title': 'Color', 'x-python-datatype': 'Enum', 'enum': [1, 2, 3]},
            'Color(3)',
            id='enum',
        ),
        pytest.param(
            [4, 5],
            {'type': 'array', 'x-python-datatype': 'deque'},
            'deque([4, 5])',
            id='deque',
        ),
        pytest.param(
            '7265bc22-ccb0-4ee2-97f0-5dd206f01ae4',
            {'type': 'string', 'x-python-datatype': 'UUID'},
            "UUID('7265bc22-ccb0-4ee2-97f0-5dd206f01ae4')",
            id='UUID',
        ),
        pytest.param(
            {'x': 'x', 'y': 10, 'u': 'http://test.com/'},
            {
                'type': 'object',
                'x-python-datatype': 'PydanticModel',
                'title': 'MyModel',
                'properties': {'u': {'type': 'string', 'x-python-datatype': 'Url'}},
            },
            "MyModel(x='x', y=10, u=Url('http://test.com/'))",
            id='pydantic_model',
        ),
        pytest.param(
            {'t': 10},
            {
                'type': 'object',
                'x-python-datatype': 'dataclass',
                'title': 'MyDataclass',
            },
            'MyDataclass(t=10)',
            id='dataclass',
        ),
        pytest.param(
            {},
            {
                'type': 'object',
                'x-python-datatype': 'dataclass',
                'title': 'MyDataclass',
            },
            'MyDataclass()',
            id='empty_dataclass',
        ),
        pytest.param(
            {'p': 20},
            {
                'type': 'object',
                'x-python-datatype': 'dataclass',
                'title': 'MyPydanticDataclass',
            },
            'MyPydanticDataclass(p=20)',
            id='pydantic_dataclass',
        ),
        pytest.param(
            'Test value error',
            {'type': 'string', 'x-python-datatype': 'Exception', 'title': 'ValueError'},
            "ValueError('Test value error')",
            id='Exception',
        ),
        pytest.param(
            {'foo': 'bar'},
            {'type': 'object', 'x-python-datatype': 'Mapping', 'title': 'MyMapping'},
            "MyMapping({'foo': 'bar'})",
            id='Mapping',
        ),
        pytest.param(
            [0, 1, 2, 3],
            {'type': 'array', 'x-python-datatype': 'Sequence', 'title': 'range'},
            'range(0, 4)',
            id='Sequence',
        ),
        pytest.param(
            [1, 2, 3],
            {'type': 'array', 'x-python-datatype': 'Sequence', 'title': 'MySequence'},
            'MySequence([1, 2, 3])',
            id='CustomSequence',
        ),
        pytest.param(
            'MyArbitraryType(12)',
            {'type': 'string', 'x-python-datatype': 'unknown'},
            'MyArbitraryType(12)',
            id='arbitrary_type',
        ),
        pytest.param(
            '<this is repr>',
            {'type': 'string', 'x-python-datatype': 'unknown'},
            '<this is repr>',
            id='repr',
        ),
        pytest.param(
            {'x': 1, 'y': 2},
            {'type': 'object', 'x-python-datatype': 'attrs', 'title': 'AttrsType'},
            'AttrsType(x=1, y=2)',
            id='attrs',
        ),
        pytest.param(
            [1, 2, 3],
            {'type': 'array', 'x-python-datatype': 'generator'},
            'generator((1, 2, 3))',
            id='generator',
        ),
    ],
)
def test_json_args_value_formatting_compact(value: Any, schema: JSONSchema, formatted_value: str):
    assert json_args_value_formatter_compact(value, schema=schema) == formatted_value


def test_all_types_covered():
    types = set(DataType.__args__)
    assert types == set(json_args_value_formatter_compact._data_type_map.keys())  # type: ignore
