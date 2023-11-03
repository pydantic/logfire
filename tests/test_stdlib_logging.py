from logging import getLogger

from logfire.integrations.logging import LogfireLoggingHandler
from logfire.testing import TestExporter


def test_stdlib_logging(exporter: TestExporter) -> None:
    logger = getLogger(__name__)
    logger.addHandler(LogfireLoggingHandler())
    logger.error('{first_name=} is in trouble!', extra={'first_name': 'Fred'})

    # insert_assert(exporter.exported_spans_as_dict(fixed_line_number=None))
    assert exporter.exported_spans_as_dict(fixed_line_number=None) == [
        {
            'name': 'first_name=Fred is in trouble!',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'error',
                'logfire.msg_template': '{first_name=} is in trouble!',
                'logfire.msg': 'first_name=Fred is in trouble!',
                'code.filepath': 'test_stdlib_logging.py',
                'code.lineno': 10,
                'code.function': 'test_stdlib_logging',
                'first_name': 'Fred',
            },
        }
    ]
