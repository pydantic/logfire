from inline_snapshot import snapshot
from opentelemetry.trace import get_current_span

import logfire
from logfire._internal.exporters.test import TestExporter
from logfire.experimental.annotations import get_traceparent, raw_annotate_span


def test_get_traceparent(exporter: TestExporter):
    with logfire.span('hi') as span:
        assert (
            get_traceparent(span)
            == get_traceparent(get_current_span())
            == snapshot('00-00000000000000000000000000000001-0000000000000001-01')
        )

    raw_annotate_span(get_traceparent(span), 'my_span_name', 'my_message', {'key': 'value'})

    # TODO there shouldn't be a pending span for the annotation
    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_annotations.py',
                    'code.function': 'test_get_traceparent',
                    'code.lineno': 123,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_annotations.py',
                    'code.function': 'test_get_traceparent',
                    'code.lineno': 123,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'my_span_name',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'pending_span',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'my_span_name',
                    'logfire.msg': 'my_message',
                    'code.filepath': 'test_annotations.py',
                    'code.function': 'test_get_traceparent',
                    'code.lineno': 123,
                    'key': 'value',
                    'logfire.disable_console_log': True,
                    'logfire.json_schema': '{"type":"object","properties":{"key":{},"logfire.span_type":{},"logfire.disable_console_log":{}}}',
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
            {
                'name': 'my_span_name',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'annotation',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'my_span_name',
                    'logfire.msg': 'my_message',
                    'code.filepath': 'test_annotations.py',
                    'code.function': 'test_get_traceparent',
                    'code.lineno': 123,
                    'key': 'value',
                    'logfire.disable_console_log': True,
                    'logfire.json_schema': '{"type":"object","properties":{"key":{},"logfire.span_type":{},"logfire.disable_console_log":{}}}',
                },
            },
        ]
    )
