import re
import sys
from typing import Any

import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.ast_utils import InspectArgumentsFailedWarning
from logfire._internal.exporters.test import TestExporter


def test_instrument_print(exporter: TestExporter, capsys: pytest.CaptureFixture[str]) -> None:
    # Logs nothing, not instrumented yet
    print('before')

    with logfire.instrument_print():
        name = 'world'
        # Puts 'name': 'world' in the attributes, but 'hello' is literal so only in the message
        print('hello', name)

        # Logs nothing, empty print() calls are ignored
        print()

        x = 1
        y = 2
        z = 3
        lst = [4, 5]
        # Puts x, y, lst in attributes
        print('hi', x, x, *lst, y)

        lst2 = [6, 7]
        # Multiple *args means we can't tell which args came from which list,
        # so we have x, z, and logfire.print_args (*lst, y, *lst2) in attributes.
        # Also test sep in message.
        print(z, x, *lst, y, *lst2, z, sep=', ')

        password = 'hunter2'
        hunter = 'my api key'
        # Scrubs based on both argument values and variable names,
        # in both attributes and message.
        print('Secret', password, hunter)

    # Logs nothing since context manager exited
    print('after uninstrument')

    # Actual raw print output, not affected by instrumentation
    assert capsys.readouterr().out == snapshot("""\
before
hello world

hi 1 1 4 5 2
3, 1, 4, 5, 2, 6, 7, 3
Secret hunter2 my api key
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
                    'logfire.msg': 'hi 1 1 4 5 2',
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_instrument_print',
                    'code.lineno': 123,
                    'y': y,
                    'x': x,
                    'lst': lst,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'y': {}, 'x': {}, 'lst': {'type': 'array'}},
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
                    'logfire.msg': '3, 1, 4, 5, 2, 6, 7, 3',
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_instrument_print',
                    'code.lineno': 123,
                    'z': z,
                    'x': x,
                    'logfire.print_args': lst + [y] + lst2,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'z': {},
                            'x': {},
                            'logfire.print_args': {'type': 'array'},
                        },
                    },
                },
            },
            {
                'name': 'print',
                'context': {'trace_id': 4, 'span_id': 4, 'is_remote': False},
                'parent': None,
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'print',
                    'logfire.msg': "Secret [Scrubbed due to 'password'] [Scrubbed due to 'api key']",
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_instrument_print',
                    'code.lineno': 123,
                    'password': "[Scrubbed due to 'password']",
                    'hunter': "[Scrubbed due to 'api key']",
                    'logfire.json_schema': {'type': 'object', 'properties': {'password': {}, 'hunter': {}}},
                    'logfire.scrubbed': [
                        {'path': ['message', 'password'], 'matched_substring': 'password'},
                        {'path': ['message', 'hunter'], 'matched_substring': 'api key'},
                        {'path': ['attributes', 'password'], 'matched_substring': 'password'},
                        {'path': ['attributes', 'hunter'], 'matched_substring': 'api key'},
                    ],
                },
            },
        ]
    )


@pytest.mark.skipif(sys.version_info < (3, 11), reason='Testing behaviour in Python 3.11+')
def test_executing_failure(exporter: TestExporter, monkeypatch: pytest.MonkeyPatch):
    warning_message = """\
Failed to introspect calling code. Please report this issue to Logfire. Using `logfire.print_args` as the fallback attribute key for all print arguments. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
`executing` failed to find a node.\
"""
    # We're about to 'disable' `executing` which `snapshot` also uses, so make the snapshot first.
    expected_spans = snapshot(
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
                    'logfire.msg': '3 set()',
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_executing_failure',
                    'code.lineno': 123,
                    'local_var': 3,
                    'logfire.json_schema': {'type': 'object', 'properties': {'local_var': {}}},
                },
            },
            {
                'name': warning_message,
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': warning_message,
                    'logfire.msg': warning_message,
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_executing_failure',
                    'code.lineno': 123,
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
                    'logfire.msg': '3 set()',
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_executing_failure',
                    'code.lineno': 123,
                    'logfire.print_args': [3, []],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'logfire.print_args': {
                                'type': 'array',
                                'x-python-datatype': 'tuple',
                                'prefixItems': [{}, {'type': 'array', 'x-python-datatype': 'set'}],
                            }
                        },
                    },
                },
            },
        ]
    )

    # Test what happens when `executing` fails.
    import executing._position_node_finder

    monkeypatch.setattr(executing._position_node_finder.PositionNodeFinder, 'find_node', lambda _: None)  # type: ignore  # pragma: no cover  (coverage being weird)

    with logfire.instrument_print():
        local_var = 3
        # The fallback heuristic works because set() has no arguments and can be ignored.
        print(local_var, set())  # type: ignore

        with pytest.warns(InspectArgumentsFailedWarning, match=re.escape(warning_message)):
            # Multiple calls with arguments break the heuristic.
            print(local_var, set([]))  # type: ignore

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == expected_spans


def test_instrument_print_no_inspect_args(
    exporter: TestExporter, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
) -> None:
    # Similar to the first test but with magic disabled.
    config_kwargs['inspect_arguments'] = False
    logfire.configure(**config_kwargs)
    with logfire.instrument_print():
        x = 1
        y = 2
        z = 3
        lst = [4, 5]
        lst2 = [6, 7]
        # Everything goes into logfire.print_args
        print(x, *lst, y, *lst2, z, sep=', ')
        password = 'hunter2'
        hunter = 'my api key'
        # Scrubbing still works, but based on argument values only.
        print('Secret', password, hunter)
        print()

    assert capsys.readouterr().out == snapshot("""\
1, 4, 5, 2, 6, 7, 3
Secret hunter2 my api key

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
                    'logfire.msg': '1, 4, 5, 2, 6, 7, 3',
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_instrument_print_no_inspect_args',
                    'code.lineno': 123,
                    'logfire.print_args': [x] + lst + [y] + lst2 + [z],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'logfire.print_args': {'type': 'array', 'x-python-datatype': 'tuple'}},
                    },
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
                    'logfire.msg': "Secret hunter2 [Scrubbed due to 'api key']",
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_instrument_print_no_inspect_args',
                    'code.lineno': 123,
                    'logfire.print_args': ['Secret', 'hunter2', "[Scrubbed due to 'api key']"],
                    'logfire.scrubbed': [
                        {'path': ['message', 'logfire.print_args'], 'matched_substring': 'api key'},
                        {'path': ['attributes', 'logfire.print_args', 2], 'matched_substring': 'api key'},
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'logfire.print_args': {'type': 'array', 'x-python-datatype': 'tuple'}},
                    },
                },
            },
        ]
    )
