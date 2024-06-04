from __future__ import annotations

import logging
from logging import Logger, getLogger
from typing import Sequence

import pytest
from dirty_equals import IsJson, IsPositiveInt
from inline_snapshot import snapshot
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Status

import logfire
from logfire.integrations.logging import LogfireLoggingHandler
from logfire.testing import TestExporter


@pytest.fixture(scope='module')
def logger() -> Logger:
    _logger = getLogger(__name__)
    _logger.addHandler(LogfireLoggingHandler())
    return _logger


def test_stdlib_logging(exporter: TestExporter, logger: Logger) -> None:
    logger.error('{first_name=} is in trouble!', extra={'first_name': 'Fred'})

    assert exporter.exported_spans_as_dict(fixed_line_number=None) == snapshot(
        [
            {
                'name': '{first_name=} is in trouble!',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': '{first_name=} is in trouble!',
                    'logfire.msg': '{first_name=} is in trouble!',
                    'code.filepath': 'test_stdlib_logging.py',
                    'code.function': 'test_stdlib_logging',
                    'code.lineno': IsPositiveInt(),
                    'first_name': 'Fred',
                    'logfire.json_schema': '{"type":"object","properties":{"first_name":{}}}',
                },
            }
        ]
    )


def test_stdlib_logging_with_positional_params(exporter: TestExporter, logger: Logger) -> None:
    logger.error('This is a test message %s.', 'with a parameter')

    assert exporter.exported_spans_as_dict(fixed_line_number=None) == snapshot(
        [
            {
                'name': 'This is a test message %s.',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'This is a test message %s.',
                    'logfire.msg': 'This is a test message with a parameter.',
                    'code.filepath': 'test_stdlib_logging.py',
                    'code.function': 'test_stdlib_logging_with_positional_params',
                    'code.lineno': IsPositiveInt(),
                    'logfire.logging_args': '["with a parameter"]',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logging_args":{"type":"array","x-python-datatype":"tuple"}}}',
                },
            }
        ]
    )


def test_stdlib_logging_with_positional_dict_param(exporter: TestExporter, logger: Logger) -> None:
    logger.error('This is a test message %s.', {'param': 'with a parameter'})

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'This is a test message %s.',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'This is a test message %s.',
                    'logfire.msg': "This is a test message {'param': 'with a parameter'}.",
                    'code.filepath': 'test_stdlib_logging.py',
                    'code.function': 'test_stdlib_logging_with_positional_dict_param',
                    'code.lineno': 123,
                    'logfire.logging_args': '[{"param":"with a parameter"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logging_args":{"type":"array","x-python-datatype":"tuple"}}}',
                },
            }
        ]
    )


def test_stdlib_logging_with_parenthesis_params(exporter: TestExporter, logger: Logger) -> None:
    logger.error('This is a test message %(module)s')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'This is a test message %(module)s',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'This is a test message %(module)s',
                    'logfire.msg': 'This is a test message %(module)s',
                    'code.filepath': 'test_stdlib_logging.py',
                    'code.function': 'test_stdlib_logging_with_parenthesis_params',
                    'code.lineno': IsPositiveInt(),
                },
            }
        ]
    )


def test_stdlib_logging_with_custom_parenthesis_params(exporter: TestExporter, logger: Logger) -> None:
    logger.error('abc %(blah)s', {'blah': 'blah'})

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'abc %(blah)s',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'abc %(blah)s',
                    'logfire.msg': 'abc blah',
                    'code.filepath': 'test_stdlib_logging.py',
                    'code.function': 'test_stdlib_logging_with_custom_parenthesis_params',
                    'code.lineno': IsPositiveInt(),
                    'blah': 'blah',
                    'logfire.json_schema': '{"type":"object","properties":{"blah":{}}}',
                },
            }
        ]
    )


def test_stdlib_logging_warning(exporter: TestExporter, logger: Logger) -> None:
    logger.warning('%s is in some trouble', 'Fred')

    assert exporter.exported_spans_as_dict(fixed_line_number=None) == snapshot(
        [
            {
                'name': '%s is in some trouble',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': '%s is in some trouble',
                    'logfire.msg': 'Fred is in some trouble',
                    'code.filepath': 'test_stdlib_logging.py',
                    'code.function': 'test_stdlib_logging_warning',
                    'code.lineno': IsPositiveInt(),
                    'logfire.logging_args': '["Fred"]',
                    'logfire.json_schema': IsJson(
                        {
                            'type': 'object',
                            'properties': {'logfire.logging_args': {'type': 'array', 'x-python-datatype': 'tuple'}},
                        }
                    ),
                },
            }
        ]
    )


def test_recursive_logging_from_opentelemetry() -> None:
    class ExceptionExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]):
            raise Exception()

    logfire.configure(
        send_to_logfire=False,
        additional_span_processors=[SimpleSpanProcessor(ExceptionExporter())],
    )

    class TestLoggingHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.logs: list[logging.LogRecord] = []
            self.emit = self.logs.append  # type: ignore

    # Add our handler to the root logger (not the logger fixture) to get internal logs from OTEL.
    logger = getLogger()
    test_logging_handler = TestLoggingHandler()
    logfire_logging_handler = LogfireLoggingHandler(fallback=test_logging_handler)
    logger.addHandler(logfire_logging_handler)

    try:
        # This calls ExceptionExporter.export which causes OTEL to log an exception.
        # That log call goes to LogfireLoggingHandler.emit, which usually tries to emit another logfire log,
        # causing another stdlib log from OTEL, potentially leading to infinite recursion.
        # Recursion is prevented by OTEL suppressing instrumentation, so the second logfire log isn't emitted.
        # But when we detect this, we use the fallback handler instead, so this tests that.
        logfire.info('test')
    finally:
        # Don't mess with the root logger longer than needed.
        logger.removeHandler(logfire_logging_handler)

    [record] = test_logging_handler.logs
    # This is the message logged by OTEL.
    assert record.message == 'Exception while exporting Span.'


def test_logging_from_opentelemetry(exporter: TestExporter) -> None:
    # Add our handler to the root logger (not the logger fixture) to get internal logs from OTEL.
    logger = getLogger()
    logfire_logging_handler = LogfireLoggingHandler()
    logger.addHandler(logfire_logging_handler)
    try:
        logger.error('test')  # sanity check

        # This causes OTEL to log a warning.
        # Unlike the test above, there's no risk of recursion since the exporter doesn't raise errors.
        # So the log appears in the exported spans below.
        Status(description=4)  # type: ignore
    finally:
        # Don't mess with the root logger longer than needed.
        logger.removeHandler(logfire_logging_handler)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'test',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'test',
                    'logfire.msg': 'test',
                    'code.filepath': 'test_stdlib_logging.py',
                    'code.function': 'test_logging_from_opentelemetry',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'Invalid status description type, expected str',
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Invalid status description type, expected str',
                    'logfire.msg': 'Invalid status description type, expected str',
                    'code.filepath': 'status.py',
                    'code.function': '__init__',
                    'code.lineno': 123,
                },
            },
        ]
    )


def test_logging_non_string(exporter: TestExporter, logger: Logger):
    logger.error(123)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': '123',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': '123',
                    'logfire.msg': '123',
                    'code.filepath': 'test_stdlib_logging.py',
                    'code.function': 'test_logging_non_string',
                    'code.lineno': 123,
                },
            }
        ]
    )
