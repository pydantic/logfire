import pytest
from inline_snapshot import snapshot

import logfire
from logfire.testing import CaptureLogfire, TestExporter, TimeGenerator


def test_reset_exported_spans(exporter: TestExporter) -> None:
    assert len(exporter.exported_spans) == 0

    logfire.info('First log!')
    assert len(exporter.exported_spans) == 1
    assert exporter.exported_spans[0].name == 'First log!'

    logfire.info('Second log!')
    assert len(exporter.exported_spans) == 2
    assert exporter.exported_spans[1].name == 'Second log!'

    exporter.clear()
    assert len(exporter.exported_spans) == 0

    logfire.info('Third log!')
    assert len(exporter.exported_spans) == 1
    assert exporter.exported_spans[0].name == 'Third log!'


def test_capfire_fixture(capfire: CaptureLogfire) -> None:
    with pytest.raises(Exception):
        with logfire.span('a span!'):
            logfire.info('a log!')
            raise Exception('an exception!')

    exporter = capfire.exporter
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'a log!',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'a log!',
                    'logfire.msg': 'a log!',
                    'code.filepath': 'test_testing.py',
                    'code.function': 'test_capfire_fixture',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'a span!',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_testing.py',
                    'code.function': 'test_capfire_fixture',
                    'code.lineno': 123,
                    'logfire.msg_template': 'a span!',
                    'logfire.msg': 'a span!',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 3000000000,
                        'attributes': {
                            'exception.type': 'Exception',
                            'exception.message': 'an exception!',
                            'exception.stacktrace': 'Exception: an exception!',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            },
        ]
    )


def test_time_generator():
    t = TimeGenerator()
    assert t() == 1000000000
    assert t() == 2000000000
    assert repr(t) == 'TimeGenerator(ns_time=2000000000)'
