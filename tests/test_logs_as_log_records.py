from __future__ import annotations

from dataclasses import replace
from typing import Any

from dirty_equals import IsStr
from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter, TestLogExporter


def test_logs_as_log_records(
    exporter: TestExporter, logs_exporter: TestLogExporter, config_kwargs: dict[str, Any]
) -> None:
    config_kwargs['advanced'] = replace(config_kwargs['advanced'], logs_as_log_records=True)
    logfire.configure(**config_kwargs)

    with logfire.span('outer'):
        logfire.info('hello {name}', name='world', _tags=['t'])
        try:
            raise ValueError('boom')
        except ValueError:
            logfire.exception('failed')

    assert [s['name'] for s in exporter.exported_spans_as_dict()] == snapshot(['outer'])
    assert logs_exporter.exported_logs_as_dicts(include_resources=False) == snapshot(
        [
            {
                'body': 'hello world',
                'severity_number': 9,
                'severity_text': 'info',
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hello {name}',
                    'logfire.msg': 'hello world',
                    'code.filepath': 'test_logs_as_log_records.py',
                    'code.function': 'test_logs_as_log_records',
                    'code.lineno': 123,
                    'name': 'world',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{}}}',
                    'logfire.tags': ('t',),
                },
                'timestamp': 3000000000,
                'observed_timestamp': 4000000000,
                'trace_id': 1,
                'span_id': 1,
                'trace_flags': 1,
            },
            {
                'body': 'failed',
                'severity_number': 17,
                'severity_text': 'error',
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'failed',
                    'logfire.msg': 'failed',
                    'code.filepath': 'test_logs_as_log_records.py',
                    'code.function': 'test_logs_as_log_records',
                    'code.lineno': 123,
                    'exception.type': 'ValueError',
                    'exception.message': 'boom',
                    'exception.stacktrace': IsStr(regex=r'(?s)Traceback.*ValueError: boom\n'),
                },
                'timestamp': 6000000000,
                'observed_timestamp': 7000000000,
                'trace_id': 1,
                'span_id': 1,
                'trace_flags': 1,
            },
        ]
    )


class UnprintableError(Exception):
    def __str__(self) -> str:
        raise RuntimeError('no str')


def test_log_record_with_unprintable_exception(logs_exporter: TestLogExporter, config_kwargs: dict[str, Any]) -> None:
    config_kwargs['advanced'] = replace(config_kwargs['advanced'], logs_as_log_records=True)
    logfire.configure(**config_kwargs)

    logfire.error('failed', _exc_info=UnprintableError())

    [log] = logs_exporter.exported_logs_as_dicts(include_resources=False)
    assert log['body'] == 'failed'
    assert log['attributes']['exception.type'] == 'UnprintableError'
    assert log['attributes']['exception.message'] == snapshot('<exception str() failed>')
    assert log['attributes']['exception.stacktrace'] == snapshot(
        'tests.test_logs_as_log_records.UnprintableError: <exception str() failed>\n'
    )


def test_log_record_with_custom_level(logs_exporter: TestLogExporter, config_kwargs: dict[str, Any]) -> None:
    config_kwargs['advanced'] = replace(config_kwargs['advanced'], logs_as_log_records=True)
    logfire.configure(**config_kwargs)

    logfire.log(25, 'custom')

    [log] = logs_exporter.exported_logs_as_dicts(include_resources=False)
    assert (log['body'], log['severity_number'], log['attributes']['logfire.level_num']) == snapshot(
        ('custom', None, 25)
    )
