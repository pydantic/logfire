from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO

from logfire.backfill import Log, PrepareBackfill, StartSpan
from logfire.exporters._file import to_json_lines


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
            resource_attributes={'telemetry.sdk.version': '1.0.0'},  # to make output deterministic
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
            resource_attributes={'telemetry.sdk.version': '1.0.0'},  # to make output deterministic
        )
        prep_backfill.write(log)
        prep_backfill.write(span.end(datetime(2023, 1, 2, 0, 0, 1)))

    output.seek(0)
    lines = [json.loads(line) for line in to_json_lines(output)]
    # insert_assert(lines)
    assert lines == [
        {
            'resourceSpans': [
                {
                    'resource': {
                        'attributes': [
                            {'key': 'telemetry.sdk.language', 'value': {'stringValue': 'python'}},
                            {'key': 'telemetry.sdk.name', 'value': {'stringValue': 'opentelemetry'}},
                            {'key': 'telemetry.sdk.version', 'value': {'stringValue': '1.0.0'}},
                            {'key': 'service.name', 'value': {'stringValue': 'docs.pydantic.dev'}},
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
                                        {'key': 'logfire.span_type', 'value': {'stringValue': 'log'}},
                                        {'key': 'logfire.level', 'value': {'stringValue': 'info'}},
                                        {'key': 'logfire.msg_template', 'value': {'stringValue': 'GET {path=}'}},
                                        {'key': 'logfire.msg', 'value': {'stringValue': 'GET /test'}},
                                        {'key': 'path', 'value': {'stringValue': '/test'}},
                                    ],
                                    'status': {'code': 'STATUS_CODE_OK'},
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
                            {'key': 'service.name', 'value': {'stringValue': 'docs.pydantic.dev'}},
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
                                        {'key': 'logfire.span_type', 'value': {'stringValue': 'log'}},
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
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    ]
