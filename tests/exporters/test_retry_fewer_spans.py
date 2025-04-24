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

from logfire._internal.exporters.otlp import (
    BodyTooLargeError,
    RetryFewerSpansSpanExporter,
)
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
                if len(spans) > 1:
                    raise BodyTooLargeError(20_000_000, 5_000_000)
                else:
                    # RetryFewerSpansSpanExporter can only split if there's >1 span.
                    return SpanExportResult.FAILURE
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
