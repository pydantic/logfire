import pytest
import structlog
from inline_snapshot import snapshot

import logfire
from logfire.integrations.structlog import LogfireProcessor
from logfire.testing import TestExporter


@pytest.fixture(autouse=True, scope='module')
def fixture_configure_structlog() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt='%Y-%m-%d %H:%M:%S', utc=False),
            LogfireProcessor(),
            structlog.dev.ConsoleRenderer(),
        ]
    )


@pytest.fixture(scope='module')
def logger() -> structlog.BoundLogger:
    return structlog.get_logger()


def test_structlog(exporter: TestExporter, logger: structlog.BoundLogger) -> None:
    logger.info('This is now being logged: %s', 123)
    logger.error(456)

    try:
        str(1 / 0)
    except ZeroDivisionError:
        logger.exception('error', **{'logfire.msg': 'bad'})

    assert exporter.exported_spans_as_dict(fixed_line_number=None) == snapshot(
        [
            {
                'name': 'This is now being logged: 123',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'This is now being logged: 123',
                    'logfire.msg': 'This is now being logged: 123',
                    'code.filepath': 'test_structlog.py',
                    'code.function': 'test_structlog',
                    'code.lineno': 31,
                    'logfire.disable_console_log': True,
                },
            },
            {
                'name': '456',
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': '456',
                    'logfire.msg': '456',
                    'code.filepath': 'test_structlog.py',
                    'code.function': 'test_structlog',
                    'code.lineno': 32,
                    'logfire.disable_console_log': True,
                },
            },
            {
                'name': 'error',
                'context': {'trace_id': 3, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'error',
                    'logfire.msg': 'bad',
                    'code.filepath': 'test_structlog.py',
                    'code.function': 'test_structlog',
                    'code.lineno': 37,
                    'logfire.disable_console_log': True,
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 4000000000,
                        'attributes': {
                            'exception.type': 'ZeroDivisionError',
                            'exception.message': 'division by zero',
                            'exception.stacktrace': 'ZeroDivisionError: division by zero',
                            'exception.escaped': 'False',
                        },
                    }
                ],
            },
        ]
    )

    for span in exporter.exported_spans:
        assert span.instrumentation_scope.name == 'logfire.structlog'  # type: ignore


def test_structlog_tags(exporter: TestExporter, logger: structlog.BoundLogger) -> None:
    logger.info('tagged', **{'logfire.tags': ['foo', 'bar']})
    logger.bind(**{'logfire.tags': ['bound']}).info('bound')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'tagged',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'tagged',
                    'logfire.msg': 'tagged',
                    'code.filepath': 'test_structlog.py',
                    'code.function': 'test_structlog_tags',
                    'code.lineno': 123,
                    'logfire.tags': ('foo', 'bar'),
                    'logfire.disable_console_log': True,
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
                    'code.filepath': 'test_structlog.py',
                    'code.function': 'test_structlog_tags',
                    'code.lineno': 123,
                    'logfire.tags': ('bound',),
                    'logfire.disable_console_log': True,
                },
            },
        ]
    )


def test_structlog_single_string_tag(exporter: TestExporter, logger: structlog.BoundLogger) -> None:
    logger.bind(**{'logfire.tags': 'production'}).info('single tag')

    [span] = exporter.exported_spans_as_dict()
    assert span['attributes']['logfire.tags'] == ('production',)


def test_structlog_tags_merged_with_instance_tags(exporter: TestExporter) -> None:
    tagged_logger = structlog.wrap_logger(
        structlog.ReturnLogger(),
        processors=[LogfireProcessor(logfire_instance=logfire.with_tags('instance'))],
    )
    tagged_logger.info('tagged', **{'logfire.tags': ['foo']})

    [span] = exporter.exported_spans_as_dict()
    assert span['attributes']['logfire.tags'] == ('instance', 'foo')


def test_structlog_critical_is_fatal(exporter: TestExporter, logger: structlog.BoundLogger) -> None:
    logger.critical('boom')

    assert exporter.exported_spans_as_dict(fixed_line_number=None) == snapshot(
        [
            {
                'name': 'boom',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 21,
                    'logfire.msg_template': 'boom',
                    'logfire.msg': 'boom',
                    'code.filepath': 'test_structlog.py',
                    'code.function': 'test_structlog_critical_is_fatal',
                    'code.lineno': 177,
                    'logfire.disable_console_log': True,
                },
            }
        ]
    )


@pytest.mark.parametrize('attributes', [{}, {'logfire.msg': None}])
def test_structlog_message_is_not_formatted(
    exporter: TestExporter, logger: structlog.BoundLogger, attributes: dict[str, str | None]
) -> None:
    logger.info('hello {name:>1000}', name='world', **attributes)

    [span] = exporter.exported_spans_as_dict()
    assert span['attributes']['logfire.msg_template'] == 'hello {name:>1000}'
    assert span['attributes']['logfire.msg'] == ('None' if attributes else 'hello {name:>1000}')


def test_structlog_keeps_log_record_named_attributes(exporter: TestExporter, logger: structlog.BoundLogger) -> None:
    # https://github.com/pydantic/logfire/issues/2865: keys that happen to share
    # a name with a stdlib LogRecord field are user attributes in a structlog
    # event dict, so they must reach Logfire.
    logger.info('user login', name='alice', module='auth', process=123, user_id=3)

    [span] = exporter.exported_spans_as_dict()
    attributes = span['attributes']
    assert attributes['name'] == 'alice'
    assert attributes['module'] == 'auth'
    assert attributes['process'] == 123
    assert attributes['user_id'] == 3
    # structlog's own keys are still stripped.
    assert 'level' not in attributes
    assert 'event' not in attributes
    assert 'timestamp' not in attributes
