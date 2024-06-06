from __future__ import annotations

from flask import Flask
from inline_snapshot import snapshot
from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware
from opentelemetry.propagate import inject
from werkzeug.test import Client

import logfire
from logfire.testing import TestExporter


def test_wsgi_middleware(exporter: TestExporter) -> None:
    app = Flask(__name__)
    app.wsgi_app = OpenTelemetryMiddleware(app.wsgi_app)

    @app.route('/')
    def homepage():  # type: ignore
        logfire.info('inside request handler')
        return 'middleware test'

    client = Client(app)
    with logfire.span('outside request handler'):
        headers: dict[str, str] = {}
        inject(headers)
        response = client.get('/', headers=headers)
        # Read the response to ensure that the OTEL middleware span ends
        # before the outer logfire span to avoid confusion.
        assert response.status_code == 200
        assert response.text == 'middleware test'

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'inside request handler',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'inside request handler',
                    'logfire.msg': 'inside request handler',
                    'code.filepath': 'test_wsgi.py',
                    'code.lineno': 123,
                    'code.function': 'homepage',
                },
            },
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 4000000000,
                'attributes': {
                    'http.method': 'GET',
                    'http.server_name': 'localhost',
                    'http.scheme': 'http',
                    'net.host.name': 'localhost',
                    'net.host.port': 80,
                    'http.host': 'localhost',
                    'http.target': '/',
                    'http.flavor': '1.1',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /',
                    'http.status_code': 200,
                },
            },
            {
                'name': 'outside request handler',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_wsgi.py',
                    'code.function': 'test_wsgi_middleware',
                    'code.lineno': 123,
                    'logfire.msg_template': 'outside request handler',
                    'logfire.msg': 'outside request handler',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )
