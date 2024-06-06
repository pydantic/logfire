from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO

import pytest
from inline_snapshot import snapshot
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from logfire._internal.backfill import Log, PrepareBackfill, StartSpan
from logfire._internal.exporters.file import FileParser, to_json_lines


def test_write_spans_and_logs() -> None:
    output = BytesIO()
    with PrepareBackfill(output, batch=False) as prep_backfill:
        span = StartSpan(
            span_name='session',
            msg_template='session {user_id=} {path=}',
            service_name='docs.pydantic.dev',
            log_attributes={'user_id': '123', 'path': '/test'},
            span_id=1,
            trace_id=2,
            start_timestamp=datetime(2023, 1, 1, 0, 0, 0),
            otel_resource_attributes={'telemetry.sdk.version': '1.0.0'},  # to make output deterministic
        )
        log = Log(
            msg_template='GET {path=}',
            level='info',
            service_name='docs.pydantic.dev',
            attributes={'path': '/test'},
            trace_id=2,
            span_id=3,
            parent_span_id=1,
            timestamp=datetime(2023, 1, 1, 0, 0, 0),
            formatted_msg='GET /test',
            otel_resource_attributes={'telemetry.sdk.version': '1.0.0'},  # to make output deterministic
        )
        prep_backfill.write(log)
        prep_backfill.write(span.end(datetime(2023, 1, 2, 0, 0, 1)))

    output.seek(0)
    lines = [json.loads(line) for line in to_json_lines(output)]
    assert lines == snapshot(
        [
            {
                'resourceSpans': [
                    {
                        'resource': {
                            'attributes': [
                                {
                                    'key': 'telemetry.sdk.language',
                                    'value': {'stringValue': 'python'},
                                },
                                {
                                    'key': 'telemetry.sdk.name',
                                    'value': {'stringValue': 'opentelemetry'},
                                },
                                {
                                    'key': 'telemetry.sdk.version',
                                    'value': {'stringValue': '1.0.0'},
                                },
                                {
                                    'key': 'service.name',
                                    'value': {'stringValue': 'docs.pydantic.dev'},
                                },
                            ]
                        },
                        'scopeSpans': [
                            {
                                'scope': {'name': 'logfire'},
                                'spans': [
                                    {
                                        'traceId': 'AAAAAAAAAAAAAAAAAAAAAg==',
                                        'spanId': 'AAAAAAAAAAM=',
                                        'parentSpanId': 'AAAAAAAAAAE=',
                                        'name': 'GET {path=}',
                                        'kind': 'SPAN_KIND_INTERNAL',
                                        'startTimeUnixNano': '1672531200000000000',
                                        'endTimeUnixNano': '1672531200000000000',
                                        'attributes': [
                                            {
                                                'key': 'logfire.span_type',
                                                'value': {'stringValue': 'log'},
                                            },
                                            {
                                                'key': 'logfire.level_num',
                                                'value': {'intValue': '9'},
                                            },
                                            {
                                                'key': 'logfire.msg_template',
                                                'value': {'stringValue': 'GET {path=}'},
                                            },
                                            {
                                                'key': 'logfire.msg',
                                                'value': {'stringValue': 'GET /test'},
                                            },
                                            {'key': 'path', 'value': {'stringValue': '/test'}},
                                        ],
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
                                {
                                    'key': 'telemetry.sdk.language',
                                    'value': {'stringValue': 'python'},
                                },
                                {
                                    'key': 'telemetry.sdk.name',
                                    'value': {'stringValue': 'opentelemetry'},
                                },
                                {
                                    'key': 'telemetry.sdk.version',
                                    'value': {'stringValue': '1.0.0'},
                                },
                                {
                                    'key': 'service.name',
                                    'value': {'stringValue': 'docs.pydantic.dev'},
                                },
                            ]
                        },
                        'scopeSpans': [
                            {
                                'scope': {'name': 'logfire'},
                                'spans': [
                                    {
                                        'traceId': 'AAAAAAAAAAAAAAAAAAAAAg==',
                                        'spanId': 'AAAAAAAAAAE=',
                                        'name': 'session',
                                        'kind': 'SPAN_KIND_INTERNAL',
                                        'startTimeUnixNano': '1672531200000000000',
                                        'endTimeUnixNano': '1672617601000000000',
                                        'attributes': [
                                            {
                                                'key': 'logfire.span_type',
                                                'value': {'stringValue': 'log'},
                                            },
                                            {
                                                'key': 'logfire.msg_template',
                                                'value': {'stringValue': 'session {user_id=} {path=}'},
                                            },
                                            {
                                                'key': 'logfire.msg',
                                                'value': {'stringValue': 'session user_id=123 path=/test'},
                                            },
                                            {'key': 'user_id', 'value': {'stringValue': '123'}},
                                            {'key': 'path', 'value': {'stringValue': '/test'}},
                                        ],
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


@pytest.mark.parametrize('read_chunk_size', [1, 10, 100, 1_000, 10_000])
def test_parser(read_chunk_size: int) -> None:
    data = BytesIO()
    with PrepareBackfill(data) as prep_backfill:
        spans: list[StartSpan] = []
        for x in range(10):
            span = StartSpan(
                span_name='session',
                msg_template='session {user_id=} {path=}',
                service_name='docs.pydantic.dev',
                log_attributes={'user_id': '123', 'path': '/test'},
                parent=spans[-1] if spans else None,
                span_id=x + 1,
                trace_id=1,
                start_timestamp=datetime(2023, 1, 1, 0, 0, x),
                otel_resource_attributes={'telemetry.sdk.version': '1.0.0'},  # to make output deterministic
            )
            spans.append(span)
        log = Log(
            msg_template='GET {path=}',
            level='info',
            service_name='docs.pydantic.dev',
            attributes={'path': '/test'},
            trace_id=2,
            span_id=3,
            parent_span_id=1,
            timestamp=datetime(2023, 1, 1, 0, 0, 0),
            formatted_msg='GET /test',
            otel_resource_attributes={'telemetry.sdk.version': '1.0.0'},  # to make output deterministic
        )
        prep_backfill.write(log)
        for span in spans:
            prep_backfill.write(span.end(datetime(2023, 1, 2, 0, 0, 1)))

    # justify the choice of read_chunk_size
    assert 1_000 < data.tell() < 10_000

    data.seek(0)

    messages: list[ExportTraceServiceRequest] = []

    parser = FileParser()
    while data.tell() < data.getbuffer().nbytes:
        for message in parser.push(data.read(read_chunk_size)):
            messages.append(message)
    parser.finish()

    read_spans = [
        span
        for message in messages
        for resource_spans in message.resource_spans
        for scope_spans in resource_spans.scope_spans
        for span in scope_spans.spans
    ]
    assert len(read_spans) == 11
