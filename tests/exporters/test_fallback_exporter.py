from __future__ import annotations

from typing import Sequence

import pytest
import requests.exceptions
from inline_snapshot import snapshot
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.util.instrumentation import (
    InstrumentationScope,
)
from opentelemetry.trace import SpanContext, SpanKind
from opentelemetry.trace.status import Status, StatusCode

from logfire._internal.exporters.fallback import FallbackSpanExporter
from logfire.testing import TestExporter


class ExceptionExporter(SpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        raise Exception('Bad, bad exporter 😉')


class ConnectionErrorExporter(SpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        raise requests.exceptions.ConnectionError('Test connection error')


class FailureExporter(SpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return SpanExportResult.FAILURE


TEST_SPAN = ReadableSpan(
    name='test',
    context=SpanContext(
        trace_id=1,
        span_id=1,
        is_remote=False,
    ),
    attributes={},
    events=[],
    links=[],
    parent=None,
    kind=SpanKind.INTERNAL,
    resource=Resource.create({'service.name': 'test', 'telemetry.sdk.version': '1.0.0'}),
    instrumentation_scope=InstrumentationScope('test'),
    status=Status(StatusCode.OK),
    start_time=0,
    end_time=1,
)


def test_fallback_on_exception() -> None:
    test_exporter = TestExporter()

    exporter = FallbackSpanExporter(ExceptionExporter(), test_exporter)
    with pytest.raises(Exception, match='Bad, bad exporter 😉'):
        exporter.export([TEST_SPAN])

    exporter.shutdown()

    assert test_exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'test',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 0,
                'end_time': 1,
                'attributes': {},
            }
        ]
    )


def test_no_fallback_on_connection_error(caplog: pytest.LogCaptureFixture) -> None:
    test_exporter = TestExporter()
    exporter = FallbackSpanExporter(ConnectionErrorExporter(), test_exporter)

    assert not test_exporter.exported_spans_as_dict()
    exporter.export([TEST_SPAN])
    assert not caplog.messages

    assert test_exporter.exported_spans_as_dict() == []


def test_fallback_on_failure() -> None:
    test_exporter = TestExporter()

    exporter = FallbackSpanExporter(FailureExporter(), test_exporter)
    exporter.export([TEST_SPAN])
    exporter.shutdown()

    assert test_exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'test',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 0,
                'end_time': 1,
                'attributes': {},
            }
        ]
    )
