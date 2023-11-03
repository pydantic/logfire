from __future__ import annotations

import json
from pathlib import Path

from google.protobuf.json_format import MessageToJson
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.util.instrumentation import (
    InstrumentationScope,
)
from opentelemetry.trace import SpanContext, SpanKind
from opentelemetry.trace.status import Status, StatusCode

import logfire
from logfire.exporters._file import FileSpanExporter

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


def test_export_to_file(tmp_path: str) -> None:
    path = Path(tmp_path) / 'spans.log'

    exporter = FileSpanExporter(path)

    exporter.export([TEST_SPAN])

    exporter.shutdown()

    assert path.exists()

    messages = list(logfire.load_spans_from_file(path))

    parsed = [json.loads(MessageToJson(message)) for message in messages]

    assert len(parsed) == 1
