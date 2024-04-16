from __future__ import annotations

from typing import Sequence

import pytest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.sdk.util.instrumentation import (
    InstrumentationScope,
)
from opentelemetry.trace import SpanContext, SpanKind
from opentelemetry.trace.status import Status, StatusCode

from logfire._internal.exporters.otlp import BodyTooLargeError, RetryFewerSpansSpanExporter
from logfire.testing import TestExporter

RESOURCE = Resource.create({'service.name': 'test', 'telemetry.sdk.version': '1.0.0'})
TEST_SPANS = [
    ReadableSpan(
        name=f'test span name {span_id}',
        context=SpanContext(
            trace_id=1,
            span_id=span_id,
            is_remote=False,
        ),
        attributes={
            'code.filepath': 'super/' * 100 + 'long/path.py',
            'code.lineno': 321,
            'code.function': 'test_function',
            'other_attribute': 'value',
        },
        events=[
            Event('test event 1', attributes={'attr1': 'value1', 'attr2': 'value2'}),
            Event('test event 2', attributes={'attr3': 'value3'}),
        ],
        links=[],
        parent=None,
        kind=SpanKind.INTERNAL,
        resource=RESOURCE,
        instrumentation_scope=InstrumentationScope('test'),
        status=Status(StatusCode.OK),
        start_time=0,
        end_time=1,
    )
    for span_id in range(1, 1001)
]
TOO_BIG_SPAN_IDS = [1, 10, 100, 500, 600, 601, 602, 603, 700, 701, 710, 800, 900, 997, 999]


class SomeSpansTooLargeExporter(TestExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            if span.context and span.context.span_id in TOO_BIG_SPAN_IDS:
                raise BodyTooLargeError(20_000_000, 5_000_000)
        return super().export(spans)


def test_retry_fewer_spans_with_some_spans_too_large(exporter: TestExporter):
    # When some spans are just too big, it should successfully export the rest, but overall report failure.
    underlying_exporter = SomeSpansTooLargeExporter()
    with pytest.raises(BodyTooLargeError):
        underlying_exporter.export(TEST_SPANS)
    assert underlying_exporter.exported_spans == []

    retry_exporter = RetryFewerSpansSpanExporter(underlying_exporter)
    res = retry_exporter.export(TEST_SPANS)
    assert res is SpanExportResult.FAILURE
    assert underlying_exporter.exported_spans == [
        span for span in TEST_SPANS if span.context and span.context.span_id not in TOO_BIG_SPAN_IDS
    ]

    # For the too big spans, `logfire.error` is called once each in place of exporting the original span.
    # In this test, the `logfire.error` call sends spans to the `exporter: TestExporter` fixture,
    # which is separate from `underlying_exporter` and `retry_exporter`.
    # In reality, one exporter would receive both the original (not too big) spans and the error logs.
    assert exporter.exported_spans_as_dict(fixed_line_number=None, strip_filepaths=False) == [
        {
            'name': 'Failed to export a span of size {size:,} bytes: {span_name}',
            'context': {'trace_id': error_log_span_id, 'span_id': error_log_span_id, 'is_remote': False},
            'parent': None,
            'start_time': error_log_span_id * 1000000000,
            'end_time': error_log_span_id * 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_num': 17,
                'logfire.msg_template': 'Failed to export a span of size {size:,} bytes: {span_name}',
                'logfire.msg': f'Failed to export a span of size 20,000,000 bytes: test span name {too_big_span_id}',
                'code.filepath': (
                    'super/super/super/super/super/super/super/super/super/super/super/super/'
                    'super/super/super/super/super/super/super/super/super/super/super/super/'
                    'supe...per/super/super/super/super/super/super/super/super/super/super/'
                    'super/super/super/super/super/super/super/super/super/super/super/super/'
                    'long/path.py'
                ),
                'code.function': 'test_function',
                'code.lineno': 321,
                'size': 20_000_000,
                'max_size': 5_000_000,
                'span_name': f'test span name {too_big_span_id}',
                'num_attributes': 4,
                'num_events': 2,
                'num_links': 0,
                'num_event_attributes': 3,
                'num_link_attributes': 0,
                'logfire.json_schema': '{"type":"object","properties":{"size":{},"max_size":{},"span_name":{},"num_attributes":{},"num_events":{},"num_links":{},"num_event_attributes":{},"num_link_attributes":{}}}',
            },
        }
        for error_log_span_id, too_big_span_id in enumerate(TOO_BIG_SPAN_IDS, start=1)
    ]

    retry_exporter.force_flush()
    retry_exporter.shutdown()


class NotTooManySpansExporter(TestExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if len(spans) > 20:
            raise BodyTooLargeError(100, 50)
        return super().export(spans)


def test_retry_fewer_spans_when_too_many():
    # When none of the spans are too big but there's just too many,
    # it should successfully export them all in smaller batches.
    test_exporter = NotTooManySpansExporter()
    with pytest.raises(BodyTooLargeError):
        test_exporter.export(TEST_SPANS)
    assert test_exporter.exported_spans == []

    exporter = RetryFewerSpansSpanExporter(test_exporter)
    res = exporter.export(TEST_SPANS)
    assert res is SpanExportResult.SUCCESS
    assert test_exporter.exported_spans == TEST_SPANS
