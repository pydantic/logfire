import json
from typing import Any, Callable

import httpx
from dirty_equals import IsDatetime, IsStr

from logfire import Logfire
from logfire.integrations.wsgi import LogfireMiddleware

from .conftest import TestExporter


def wsgi(environ: dict[str, Any], start_response: Callable[..., None]) -> list[bytes]:
    status = '200 OK'
    headers = [('Content-type', 'text/plain')]
    start_response(status, headers)
    return [b'Hello, World!']


def test_wsgi_middleware(logfire: Logfire, exporter: TestExporter) -> None:
    app = LogfireMiddleware(wsgi=wsgi, logfire=logfire)

    with httpx.Client(app=app, base_url='http://testserver') as client:
        response = client.get('/')
        assert response.status_code == 200
        assert response.text == 'Hello, World!'

    exported_spans = [json.loads(span.to_json()) for span in exporter.exported_spans]
    # insert_assert(exported_spans)
    assert exported_spans == [
        {
            'name': 'GET /',
            'context': {
                'trace_id': IsStr(),
                'span_id': IsStr(),
                'trace_state': '[]',
            },
            'kind': 'SpanKind.INTERNAL',
            'parent_id': IsStr(),
            'start_time': IsDatetime(iso_string=True),
            'end_time': IsDatetime(iso_string=True),
            'status': {'status_code': 'UNSET'},
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': '{method} {path}',
                'http.method': 'GET',
                'http.server_name': 'testserver',
                'http.scheme': 'http',
                'net.host.port': 80,
                'http.host': 'testserver',
                'http.url': 'http://testserver/',
                'net.peer.ip': '127.0.0.1',
                'http.user_agent': f'python-httpx/{httpx.__version__}',
                'http.flavor': '1.1',
                'method': 'GET',
                'path': '/',
            },
            'events': [],
            'links': [],
            'resource': {'attributes': {'service.name': 'logfire-sdk-testing'}, 'schema_url': ''},
        },
        {
            'name': 'GET /',
            'context': {
                'trace_id': IsStr(),
                'span_id': IsStr(),
                'trace_state': '[]',
            },
            'kind': 'SpanKind.INTERNAL',
            'parent_id': None,
            'start_time': IsDatetime(iso_string=True),
            'end_time': IsDatetime(iso_string=True),
            'status': {'status_code': 'UNSET'},
            'attributes': {'logfire.log_type': 'real_span'},
            'events': [],
            'links': [],
            'resource': {'attributes': {'service.name': 'logfire-sdk-testing'}, 'schema_url': ''},
        },
    ]
