from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import loguru
import pytest
from inline_snapshot import snapshot
from loguru import logger

import logfire
from logfire import ConsoleOptions, loguru_handler
from logfire.integrations.loguru import LogfireHandler
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
                    'code.lineno': 25,
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
                    'code.lineno': 26,
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
                    'code.lineno': 31,
                    'logfire.logger_name': 'tests.test_loguru',
                    'foo': 'bar',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{},"foo":{}}}',
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
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
                    'code.lineno': 33,
                    'logfire.logger_name': 'tests.test_loguru',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{}}}',
                },
            },
        ]
    )

    for span in exporter.exported_spans:
        assert span.instrumentation_scope.name == 'logfire.loguru'  # type: ignore


def test_loguru_tags(exporter: TestExporter) -> None:
    logger.info('Hello {name}', name='World', **{'logfire.tags': ['foo', 'bar']})
    logger.bind(**{'logfire.tags': ['bound']}).info('bound')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Hello {name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'Hello {name}',
                    'logfire.msg': 'Hello World',
                    'code.filepath': 'test_loguru.py',
                    'code.function': 'test_loguru_tags',
                    'code.lineno': 123,
                    'logfire.logger_name': 'tests.test_loguru',
                    'name': 'World',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{},"name":{}}}',
                    'logfire.tags': ('foo', 'bar'),
                },
            },
            {
                'name': 'bound',
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'bound',
                    'logfire.msg': 'bound',
                    'code.filepath': 'test_loguru.py',
                    'code.function': 'test_loguru_tags',
                    'code.lineno': 123,
                    'logfire.logger_name': 'tests.test_loguru',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{}}}',
                    'logfire.tags': ('bound',),
                },
            },
        ]
    )


def test_loguru_single_string_tag(exporter: TestExporter) -> None:
    logger.bind(**{'logfire.tags': 'production'}).info('single tag')

    [span] = exporter.exported_spans_as_dict()
    assert span['attributes']['logfire.tags'] == ('production',)


@contextmanager
def loguru_handlers(*handlers: Any) -> Generator[None]:
    logger.configure(handlers=list(handlers))
    try:
        yield
    finally:
        logger.configure(handlers=[loguru_handler()])


def test_loguru_console_log_false(exporter: TestExporter) -> None:
    with loguru_handlers(loguru_handler(console_log=False)):
        logger.info('quiet')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'quiet',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'quiet',
                    'logfire.msg': 'quiet',
                    'code.filepath': 'test_loguru.py',
                    'code.function': 'test_loguru_console_log_false',
                    'code.lineno': 123,
                    'logfire.logger_name': 'tests.test_loguru',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.logger_name":{}}}',
                    'logfire.disable_console_log': True,
                },
            }
        ]
    )


@pytest.mark.parametrize('console_log,disabled', [(None, True), (True, None), (False, True)])
def test_loguru_console_log_overrides_instance_setting(
    exporter: TestExporter, console_log: bool | None, disabled: bool | None
) -> None:
    sink = LogfireHandler(logfire_instance=logfire.with_settings(console_log=False), console_log=console_log)
    with loguru_handlers({'sink': sink, 'format': '{message}'}):
        logger.info('quiet')

    [span] = exporter.exported_spans_as_dict()
    assert span['attributes'].get('logfire.disable_console_log') == disabled


@pytest.mark.parametrize(
    'console_log,expected',
    [
        (True, ['LOGURU | From Loguru', 'From Loguru', 'From Logfire']),
        (False, ['LOGURU | From Loguru', 'From Logfire']),
    ],
)
def test_loguru_console_output(
    capsys: pytest.CaptureFixture[str],
    exporter: TestExporter,
    config_kwargs: dict[str, Any],
    console_log: bool,
    expected: list[str],
) -> None:
    config_kwargs['console'] = ConsoleOptions(colors='never', include_timestamps=False)
    logfire.configure(**config_kwargs)
    loguru_sink = {'sink': sys.stdout, 'format': 'LOGURU | {message}'}

    with loguru_handlers(loguru_sink, loguru_handler(console_log=console_log)):
        logger.info('From Loguru')
        logfire.info('From Logfire')

    assert capsys.readouterr().out.splitlines() == expected
    assert [span['name'] for span in exporter.exported_spans_as_dict()] == ['From Loguru', 'From Logfire']
