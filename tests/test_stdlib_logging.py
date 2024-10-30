from __future__ import annotations

import logging
from contextlib import contextmanager
from logging import Logger, getLogger
from typing import Any, Sequence

import pytest
from dirty_equals import IsPositiveInt
from inline_snapshot import snapshot
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
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
                    'logfire.logger_name': 'tests.test_stdlib_logging',
                    'logfire.json_schema': '{"type":"object","properties":{"first_name":{},"logfire.logger_name":{}}}',
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
                    'logfire.logger_name': 'tests.test_stdlib_logging',
                    'logfire.logging_args': '["with a parameter"]',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{},"logfire.logging_args":{"type":"array","x-python-datatype":"tuple"}}}',
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
                    'logfire.logger_name': 'tests.test_stdlib_logging',
                    'logfire.logging_args': '[{"param":"with a parameter"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{},"logfire.logging_args":{"type":"array","x-python-datatype":"tuple"}}}',
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
                    'logfire.logger_name': 'tests.test_stdlib_logging',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{}}}',
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
                    'logfire.logger_name': 'tests.test_stdlib_logging',
                    'blah': 'blah',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{},"blah":{}}}',
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
                    'logfire.logger_name': 'tests.test_stdlib_logging',
                    'logfire.logging_args': '["Fred"]',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{},"logfire.logging_args":{"type":"array","x-python-datatype":"tuple"}}}',
                },
            }
        ]
    )


class MockLoggingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs: list[logging.LogRecord] = []
        self.emit = self.logs.append  # type: ignore


@contextmanager
def logfire_logging_handler_on_root_logger():
    # Add our handler to the root logger (not the logger fixture) to get internal logs from OTEL.
    logger = getLogger()
    test_logging_handler = MockLoggingHandler()
    logfire_logging_handler = LogfireLoggingHandler(fallback=test_logging_handler)
    logger.addHandler(logfire_logging_handler)
    try:
        yield test_logging_handler
    finally:
        # Don't mess with the root logger longer than needed.
        logger.removeHandler(logfire_logging_handler)


def test_recursive_logging_from_opentelemetry() -> None:
    class ExceptionExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]):
            raise Exception()

    logfire.configure(
        send_to_logfire=False,
        additional_span_processors=[SimpleSpanProcessor(ExceptionExporter())],
    )

    with logfire_logging_handler_on_root_logger() as test_logging_handler:
        # This calls ExceptionExporter.export which causes OTEL to log an exception.
        # That log call goes to LogfireLoggingHandler.emit, which usually tries to emit another logfire log,
        # causing another stdlib log from OTEL, potentially leading to infinite recursion.
        # Recursion is prevented by OTEL suppressing instrumentation, so the second logfire log isn't emitted.
        # But when we detect this, we use the fallback handler instead, so this tests that.
        logfire.info('test')

    [record] = test_logging_handler.logs
    # This is the message logged by OTEL.
    assert record.message == 'Exception while exporting Span.'


def test_recursive_logging_from_batch_span_processor(exporter: TestExporter, config_kwargs: dict[str, Any]) -> None:
    config_kwargs = {
        **config_kwargs,
        'additional_span_processors': [BatchSpanProcessor(exporter, max_queue_size=1, max_export_batch_size=1)],
    }
    logfire.configure(**config_kwargs)

    with logfire_logging_handler_on_root_logger() as test_logging_handler:
        for _ in range(1000):  # just preventing an infinite loop, this should break much sooner.  # pragma: no branch
            if test_logging_handler.logs:
                # Stop when we get the log we want caused by a full queue.
                # It's not easy to predict when this will happen since the queue is processed in a separate thread.
                break
            logfire.info('test')

    logfire.force_flush()

    [record] = test_logging_handler.logs
    # This is the message logged by OTEL, in BatchSpanProcessor.on_end.
    # We're testing that it doesn't get converted to a logfire log by LogfireLoggingHandler.
    # To prevent that, MainSpanProcessorWrapper.on_end uses suppress_instrumentation.
    assert record.message == 'Queue is full, likely spans will be dropped.'

    # Ensure that we got some of the spans from `logfire.info('test')` above and nothing else.
    assert exporter.exported_spans
    for span in exporter.exported_spans:
        assert span.name == 'test'

    exporter.clear()

    logfire.shutdown()

    with logfire_logging_handler_on_root_logger() as test_logging_handler:
        logfire.info('spans after shutdown are dropped')

    [record] = test_logging_handler.logs
    # This is the message logged by OTEL, in BatchSpanProcessor.on_end, same as above.
    assert record.message == 'Already shutdown, dropping span.'

    assert not exporter.exported_spans


def test_logging_from_opentelemetry(exporter: TestExporter) -> None:
    with logfire_logging_handler_on_root_logger() as test_logging_handler:
        logging.error('test')  # sanity check

        # This causes OTEL to log a warning.
        # Unlike the test_recursive_logging* tests above,
        # there's no risk of recursion since the exporter doesn't raise errors.
        # So the log appears in the exported spans below.
        Status(description=4)  # type: ignore

    assert not test_logging_handler.logs

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
                    'logfire.logger_name': 'root',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{}}}',
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
                    'logfire.logger_name': 'opentelemetry.trace.status',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{}}}',
                },
            },
        ]
    )

    for span in exporter.exported_spans:
        assert span.instrumentation_scope.name == 'logfire.stdlib.logging'  # type: ignore


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
                    'logfire.logger_name': 'tests.test_stdlib_logging',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{}}}',
                },
            }
        ]
    )
