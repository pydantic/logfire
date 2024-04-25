from logging import Logger
from typing import Any

import pytest
import structlog

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
def logger() -> Any:
    return structlog.get_logger()


def test_structlog(exporter: TestExporter, logger: Logger) -> None:
    logger.info('This is now being logged.')
    # insert_assert(exporter.exported_spans_as_dict(fixed_line_number=None))
    assert exporter.exported_spans_as_dict(fixed_line_number=None) == [
        {
            'name': 'This is now being logged.',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_num': 9,
                'logfire.msg_template': 'This is now being logged.',
                'logfire.msg': 'This is now being logged.',
                'code.filepath': 'python.py',
                'code.function': 'pytest_pyfunc_call',
                'code.lineno': 195,
                'logfire.disable_console_log': True,
            },
        }
    ]
