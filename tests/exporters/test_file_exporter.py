from __future__ import annotations

import json
from pathlib import Path

from google.protobuf.json_format import MessageToJson
from inline_snapshot import snapshot
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.util.instrumentation import (
    InstrumentationScope,
)
from opentelemetry.trace import SpanContext, SpanKind
from opentelemetry.trace.status import Status, StatusCode

import logfire
from logfire._internal.exporters.file import FileSpanExporter

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

    # the fact that we were able to read here means the file was closed
    messages = list(logfire.load_spans_from_file(path))

    parsed = [json.loads(MessageToJson(message)) for message in messages]

    assert parsed == snapshot(
        [
            {
                'resourceSpans': [
                    {
                        'resource': {
                            'attributes': [
                                {'key': 'telemetry.sdk.language', 'value': {'stringValue': 'python'}},
                                {'key': 'telemetry.sdk.name', 'value': {'stringValue': 'opentelemetry'}},
                                {'key': 'telemetry.sdk.version', 'value': {'stringValue': '1.0.0'}},
                                {'key': 'service.name', 'value': {'stringValue': 'test'}},
                            ]
                        },
                        'scopeSpans': [
                            {
                                'scope': {'name': 'test'},
                                'spans': [
                                    {
                                        'traceId': 'AAAAAAAAAAAAAAAAAAAAAQ==',
                                        'spanId': 'AAAAAAAAAAE=',
                                        'name': 'test',
                                        'kind': 'SPAN_KIND_INTERNAL',
                                        'endTimeUnixNano': '1',
                                        'status': {'code': 'STATUS_CODE_OK'},
                                        'flags': 256,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ]
    )


def test_dont_close_open_file(tmp_path: str) -> None:
    path = Path(tmp_path) / 'spans.log'

    with open(path, 'wb+') as file:
        exporter = FileSpanExporter(file)

        exporter.export([TEST_SPAN])

        exporter.shutdown()

        assert path.exists()

        file.seek(0)

        messages = list(logfire.load_spans_from_file(file))

        parsed = [json.loads(MessageToJson(message)) for message in messages]

        assert parsed == snapshot(
            [
                {
                    'resourceSpans': [
                        {
                            'resource': {
                                'attributes': [
                                    {'key': 'telemetry.sdk.language', 'value': {'stringValue': 'python'}},
                                    {'key': 'telemetry.sdk.name', 'value': {'stringValue': 'opentelemetry'}},
                                    {'key': 'telemetry.sdk.version', 'value': {'stringValue': '1.0.0'}},
                                    {'key': 'service.name', 'value': {'stringValue': 'test'}},
                                ]
                            },
                            'scopeSpans': [
                                {
                                    'scope': {'name': 'test'},
                                    'spans': [
                                        {
                                            'traceId': 'AAAAAAAAAAAAAAAAAAAAAQ==',
                                            'spanId': 'AAAAAAAAAAE=',
                                            'name': 'test',
                                            'kind': 'SPAN_KIND_INTERNAL',
                                            'endTimeUnixNano': '1',
                                            'status': {'code': 'STATUS_CODE_OK'},
                                            'flags': 256,
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ]
        )


def test_export_existing_file(tmp_path: str) -> None:
    path = Path(tmp_path) / 'spans.log'

    exporter = FileSpanExporter(path)
    exporter.shutdown()
    exporter = FileSpanExporter(path)
    exporter.export([TEST_SPAN])
    exporter.shutdown()
    exporter = FileSpanExporter(path)
    exporter.export([TEST_SPAN])
    exporter.shutdown()
    exporter = FileSpanExporter(path)
    exporter.shutdown()

    assert path.exists()

    messages = list(logfire.load_spans_from_file(path))

    parsed = [json.loads(MessageToJson(message)) for message in messages]

    assert parsed == snapshot(
        [
            {
                'resourceSpans': [
                    {
                        'resource': {
                            'attributes': [
                                {'key': 'telemetry.sdk.language', 'value': {'stringValue': 'python'}},
                                {'key': 'telemetry.sdk.name', 'value': {'stringValue': 'opentelemetry'}},
                                {'key': 'telemetry.sdk.version', 'value': {'stringValue': '1.0.0'}},
                                {'key': 'service.name', 'value': {'stringValue': 'test'}},
                            ]
                        },
                        'scopeSpans': [
                            {
                                'scope': {'name': 'test'},
                                'spans': [
                                    {
                                        'traceId': 'AAAAAAAAAAAAAAAAAAAAAQ==',
                                        'spanId': 'AAAAAAAAAAE=',
                                        'name': 'test',
                                        'kind': 'SPAN_KIND_INTERNAL',
                                        'endTimeUnixNano': '1',
                                        'status': {'code': 'STATUS_CODE_OK'},
                                        'flags': 256,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            {
                'resourceSpans': [
                    {
                        'resource': {
                            'attributes': [
                                {'key': 'telemetry.sdk.language', 'value': {'stringValue': 'python'}},
                                {'key': 'telemetry.sdk.name', 'value': {'stringValue': 'opentelemetry'}},
                                {'key': 'telemetry.sdk.version', 'value': {'stringValue': '1.0.0'}},
                                {'key': 'service.name', 'value': {'stringValue': 'test'}},
                            ]
                        },
                        'scopeSpans': [
                            {
                                'scope': {'name': 'test'},
                                'spans': [
                                    {
                                        'traceId': 'AAAAAAAAAAAAAAAAAAAAAQ==',
                                        'spanId': 'AAAAAAAAAAE=',
                                        'name': 'test',
                                        'kind': 'SPAN_KIND_INTERNAL',
                                        'endTimeUnixNano': '1',
                                        'status': {'code': 'STATUS_CODE_OK'},
                                        'flags': 256,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        ]
    )
