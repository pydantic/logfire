from logging import Logger, getLogger

import pytest
from dirty_equals import IsJson, IsPositiveInt

from logfire.integrations.logging import LogfireLoggingHandler
from logfire.testing import TestExporter


@pytest.fixture(scope='module')
def logger() -> Logger:
    _logger = getLogger(__name__)
    _logger.addHandler(LogfireLoggingHandler())
    return _logger


def test_stdlib_logging(exporter: TestExporter, logger: Logger) -> None:
    logger.error('{first_name=} is in trouble!', extra={'first_name': 'Fred'})

    # insert_assert(exporter.exported_spans_as_dict(fixed_line_number=None))
    assert exporter.exported_spans_as_dict(fixed_line_number=None) == [
        {
            'name': '{first_name=} is in trouble!',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'error',
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


def test_stdlib_logging_with_positional_params(exporter: TestExporter, logger: Logger) -> None:
    logger.error('This is a test message %s.', 'with a parameter')

    # insert_assert(exporter.exported_spans_as_dict(fixed_line_number=None))
    assert exporter.exported_spans_as_dict(fixed_line_number=None) == [
        {
            'name': 'This is a test message %s.',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'error',
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


def test_stdlib_logging_with_parenthesis_params(exporter: TestExporter, logger: Logger) -> None:
    logger.error('This is a test message %(module)s')

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'This is a test message %(module)s',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'error',
                'logfire.level_num': 17,
                'logfire.msg_template': 'This is a test message %(module)s',
                'logfire.msg': 'This is a test message %(module)s',
                'code.filepath': 'test_stdlib_logging.py',
                'code.function': 'test_stdlib_logging_with_parenthesis_params',
                'code.lineno': IsPositiveInt(),
            },
        }
    ]


def test_stdlib_logging_with_custom_parenthesis_params(exporter: TestExporter, logger: Logger) -> None:
    logger.error('abc %(blah)s', {'blah': 'blah'})

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'abc %(blah)s',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'error',
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


def test_stdlib_logging_warning(exporter: TestExporter, logger: Logger) -> None:
    logger.warning('%s is in some trouble', 'Fred')

    # insert_assert(exporter.exported_spans_as_dict(fixed_line_number=None))
    assert exporter.exported_spans_as_dict(fixed_line_number=None) == [
        {
            'name': '%s is in some trouble',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'warning',
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
