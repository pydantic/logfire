from __future__ import annotations

from typing import Any

import loguru
import pytest
from inline_snapshot import snapshot
from loguru import logger

from logfire import loguru_handler
from logfire.testing import TestExporter


@pytest.fixture(scope='module', autouse=True)
def configure_logger() -> Any:
    loguru.logger.configure(handlers=[loguru_handler()])


def test_loguru(exporter: TestExporter) -> None:
    logger.success('Positional arguments are merged to the message: {}', 'positional')
    logger.info('Keyword arguments are stored in the "extra", we extra them from there: {name}', name='named')

    try:
        raise ValueError('This is a test exception')
    except ValueError as e:
        logger.exception('An exception was raised: {foo}', foo='bar')
        # Test logging a non-string message.
        logger.warning(e)

    assert exporter.exported_spans_as_dict(fixed_line_number=None) == snapshot(
        [
            {
                'name': 'Positional arguments are merged to the message: {}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 11,
                    'logfire.msg_template': 'Positional arguments are merged to the message: {}',
                    'logfire.msg': 'Positional arguments are merged to the message: positional',
                    'code.filepath': 'test_loguru.py',
                    'code.function': 'test_loguru',
                    'code.lineno': 20,
                    'logfire.logger_name': 'tests.test_loguru',
                    'logfire.logging_args': '["positional"]',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{},"logfire.logging_args":{"type":"array","x-python-datatype":"tuple"}}}',
                },
            },
            {
                'name': 'Keyword arguments are stored in the "extra", we extra them from there: {name}',
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'Keyword arguments are stored in the "extra", we extra them from there: {name}',
                    'logfire.msg': 'Keyword arguments are stored in the "extra", we extra them from there: named',
                    'code.filepath': 'test_loguru.py',
                    'code.function': 'test_loguru',
                    'code.lineno': 21,
                    'logfire.logger_name': 'tests.test_loguru',
                    'name': 'named',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{},"name":{}}}',
                },
            },
            {
                'name': 'An exception was raised: {foo}',
                'context': {'trace_id': 3, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'An exception was raised: {foo}',
                    'logfire.msg': 'An exception was raised: bar',
                    'code.filepath': 'test_loguru.py',
                    'code.function': 'test_loguru',
                    'code.lineno': 26,
                    'logfire.logger_name': 'tests.test_loguru',
                    'foo': 'bar',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{},"foo":{}}}',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 4000000000,
                        'attributes': {
                            'exception.type': 'ValueError',
                            'exception.message': 'This is a test exception',
                            'exception.stacktrace': 'ValueError: This is a test exception',
                            'exception.escaped': 'False',
                        },
                    }
                ],
            },
            {
                'name': 'This is a test exception',
                'context': {'trace_id': 4, 'span_id': 4, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'This is a test exception',
                    'logfire.msg': 'This is a test exception',
                    'code.filepath': 'test_loguru.py',
                    'code.function': 'test_loguru',
                    'code.lineno': 28,
                    'logfire.logger_name': 'tests.test_loguru',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{}}}',
                },
            },
        ]
    )

    for span in exporter.exported_spans:
        assert span.instrumentation_scope.name == 'logfire.loguru'  # type: ignore
