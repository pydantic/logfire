import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.exporters.test import TestExporter


def test_instrument_print(exporter: TestExporter, capsys: pytest.CaptureFixture[str]) -> None:
    print('before')
    with logfire.instrument_print():
        name = 'world'
        print('hello', name)
        print()
        x = 1
        y = 2
        z = 3
        lst = [4, 5]
        lst2 = [6, 7]
        print(x, *lst, y)
        print(x, *lst, y, *lst2, z, sep=', ')
    print('after uninstrument')

    assert capsys.readouterr().out == snapshot("""\
before
hello world

1 4 5 2
1, 4, 5, 2, 6, 7, 3
after uninstrument
""")

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'print',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'print',
                    'logfire.msg': 'hello world',
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_instrument_print',
                    'code.lineno': 123,
                    'name': 'world',
                    'logfire.json_schema': {'type': 'object', 'properties': {'name': {}}},
                },
            },
            {
                'name': 'print',
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'print',
                    'logfire.msg': '1 4 5 2',
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_instrument_print',
                    'code.lineno': 123,
                    'y': 2,
                    'x': 1,
                    'lst': [4, 5],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'y': {}, 'x': {}, 'lst': {'type': 'array', 'x-python-datatype': 'tuple'}},
                    },
                },
            },
            {
                'name': 'print',
                'context': {'trace_id': 3, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'print',
                    'logfire.msg': '1, 4, 5, 2, 6, 7, 3',
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_instrument_print',
                    'code.lineno': 123,
                    'z': 3,
                    'x': 1,
                    '*args': [4, 5, 2, 6, 7],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'z': {}, 'x': {}, '*args': {'type': 'array', 'x-python-datatype': 'tuple'}},
                    },
                },
            },
        ]
    )
