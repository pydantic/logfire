import asyncio
from asyncio.events import Handle

import pytest
from dirty_equals import IsInt, IsJson
from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter
from tests.import_used_for_tests.slow_async_callbacks_example import main


def test_slow_async_callbacks(exporter: TestExporter) -> None:
    assert Handle._run.__qualname__ == 'Handle._run'

    # There a many small async callbacks called internally by asyncio.
    # Because of the deterministic timestamp generator, they all appear to take 1 second.
    # So we set the duration to 2 to filter for our own functions which call `mock_block`,
    # i.e. advancing the timestamp generator.
    with logfire.log_slow_async_callbacks(slow_duration=2):
        # Check that the patching is in effect
        assert Handle._run.__qualname__ == 'log_slow_callbacks.<locals>.patched_run'

        with pytest.raises(RuntimeError):
            asyncio.run(main())

    # Check that the patching is no longer in effect
    assert Handle._run.__qualname__ == 'Handle._run'

    assert exporter.exported_spans[0].instrumentation_scope.name == 'logfire.asyncio'  # type: ignore

    assert exporter.exported_spans_as_dict(fixed_line_number=None) == snapshot(
        [
            {
                'name': 'Async {name} blocked for {duration:.3f} seconds',
                'context': {'trace_id': IsInt, 'span_id': IsInt, 'is_remote': False},
                'parent': None,
                'start_time': IsInt,
                'end_time': IsInt,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Async {name} blocked for {duration:.3f} seconds',
                    'logfire.msg': 'Async callback mock_block blocked for 2.000 seconds',
                    'code.filepath': 'slow_async_callbacks_example.py',
                    'code.function': 'mock_block',
                    'code.lineno': 31,
                    'duration': 2.0,
                    'name': 'callback mock_block',
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"name":{}}}',
                },
            },
            {
                'name': 'Async {name} blocked for {duration:.3f} seconds',
                'context': {'trace_id': IsInt, 'span_id': IsInt, 'is_remote': False},
                'parent': None,
                'start_time': IsInt,
                'end_time': IsInt,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Async {name} blocked for {duration:.3f} seconds',
                    'logfire.msg': 'Async task foo 1 (foo) blocked for 2.000 seconds',
                    'code.filepath': 'slow_async_callbacks_example.py',
                    'code.function': 'foo',
                    'code.lineno': 28,
                    'duration': 2.0,
                    'name': 'task foo 1 (foo)',
                    'stack': IsJson(
                        [
                            {
                                'code.filepath': 'tests/import_used_for_tests/slow_async_callbacks_example.py',
                                'code.function': 'foo',
                                'code.lineno': 28,
                            }
                        ]
                    ),
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"name":{},"stack":{"type":"array"}}}',
                },
            },
            {
                'name': 'Async {name} blocked for {duration:.3f} seconds',
                'context': {'trace_id': IsInt, 'span_id': IsInt, 'is_remote': False},
                'parent': None,
                'start_time': IsInt,
                'end_time': IsInt,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Async {name} blocked for {duration:.3f} seconds',
                    'logfire.msg': 'Async task bar 1 (bar) blocked for 2.000 seconds',
                    'code.filepath': 'slow_async_callbacks_example.py',
                    'code.function': 'bar',
                    'code.lineno': 15,
                    'duration': 2.0,
                    'name': 'task bar 1 (bar)',
                    'stack': IsJson(
                        [
                            {
                                'code.filepath': 'tests/import_used_for_tests/slow_async_callbacks_example.py',
                                'code.function': 'bar',
                                'code.lineno': 15,
                            },
                            {
                                'code.filepath': 'tests/import_used_for_tests/slow_async_callbacks_example.py',
                                'code.function': 'foo',
                                'code.lineno': 28,
                            },
                        ]
                    ),
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"name":{},"stack":{"type":"array"}}}',
                },
            },
            {
                'name': 'Async {name} blocked for {duration:.3f} seconds',
                'context': {'trace_id': IsInt, 'span_id': IsInt, 'is_remote': False},
                'parent': None,
                'start_time': IsInt,
                'end_time': IsInt,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Async {name} blocked for {duration:.3f} seconds',
                    'logfire.msg': 'Async task bar 1 (bar) blocked for 3.000 seconds',
                    'code.filepath': 'slow_async_callbacks_example.py',
                    'code.function': 'bar',
                    'code.lineno': 18,
                    'duration': 3.0,
                    'name': 'task bar 1 (bar)',
                    'stack': IsJson(
                        [
                            {
                                'code.filepath': 'tests/import_used_for_tests/slow_async_callbacks_example.py',
                                'code.function': 'bar',
                                'code.lineno': 18,
                            }
                        ]
                    ),
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"name":{},"stack":{"type":"array"}}}',
                },
            },
            {
                'name': 'Async {name} blocked for {duration:.3f} seconds',
                'context': {'trace_id': IsInt, 'span_id': IsInt, 'is_remote': False},
                'parent': None,
                'start_time': IsInt,
                'end_time': IsInt,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Async {name} blocked for {duration:.3f} seconds',
                    'logfire.msg': 'Async task foo 2 (foo) blocked for 2.000 seconds',
                    'code.filepath': 'slow_async_callbacks_example.py',
                    'code.function': 'foo',
                    'code.lineno': 28,
                    'duration': 2.0,
                    'name': 'task foo 2 (foo)',
                    'stack': IsJson(
                        [
                            {
                                'code.filepath': 'tests/import_used_for_tests/slow_async_callbacks_example.py',
                                'code.function': 'foo',
                                'code.lineno': 28,
                            }
                        ]
                    ),
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"name":{},"stack":{"type":"array"}}}',
                },
            },
            {
                'name': 'Async {name} blocked for {duration:.3f} seconds',
                'context': {'trace_id': IsInt, 'span_id': IsInt, 'is_remote': False},
                'parent': None,
                'start_time': IsInt,
                'end_time': IsInt,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Async {name} blocked for {duration:.3f} seconds',
                    'logfire.msg': 'Async task bar 1 (bar) blocked for 4.000 seconds',
                    'code.filepath': 'slow_async_callbacks_example.py',
                    'code.function': 'bar',
                    'code.lineno': 14,
                    'duration': 4.0,
                    'name': 'task bar 1 (bar)',
                    'stack': IsJson(
                        [
                            {
                                'code.filepath': 'tests/import_used_for_tests/slow_async_callbacks_example.py',
                                'code.function': 'bar',
                                'code.lineno': 14,
                            }
                        ]
                    ),
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"name":{},"stack":{"type":"array"}}}',
                },
            },
        ]
    )
