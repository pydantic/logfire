import pytest
import structlog
from inline_snapshot import snapshot

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
                    'code.lineno': 30,
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
                    'code.lineno': 31,
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
                    'code.lineno': 36,
                    'logfire.disable_console_log': True,
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
