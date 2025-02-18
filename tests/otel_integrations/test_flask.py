import importlib
from unittest import mock

import opentelemetry.instrumentation.flask
import pytest
from flask import Flask
from inline_snapshot import snapshot
from opentelemetry.propagate import inject
from werkzeug.test import Client

import logfire
import logfire._internal.integrations.flask
from logfire.testing import TestExporter, TimeGenerator


def test_flask_instrumentation(exporter: TestExporter, time_generator: TimeGenerator) -> None:
    app = Flask(__name__)
    logfire.instrument_flask(app)

    @app.route('/')
    def homepage():  # type: ignore
        logfire.info('inside request handler')
        return 'middleware test'

    client = Client(app)
    with logfire.span('outside request handler'):
        headers: dict[str, str] = {}
        inject(headers)

        # FlaskInstrumentor sets start_time=time_ns() directly, so our ns_timestamp_generator is not used.
        old_time_ns = opentelemetry.instrumentation.flask.time_ns
        opentelemetry.instrumentation.flask.time_ns = time_generator
        try:
            response = client.get('/', headers=headers)
        finally:
            opentelemetry.instrumentation.flask.time_ns = old_time_ns

    assert response.status_code == 200
    assert response.text == 'middleware test'

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'outside request handler',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_flask.py',
                    'code.function': 'test_flask_instrumentation',
                    'code.lineno': 123,
                    'logfire.msg_template': 'outside request handler',
                    'logfire.msg': 'outside request handler',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'GET /',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'localhost',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'net.host.name': 'localhost',
                    'server.address': 'localhost',
                    'net.host.port': 80,
                    'http.host': 'localhost',
                    'server.port': 80,
                    'http.target': '/',
                    'url.path': '/',
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.route': '/',
                    'logfire.span_type': 'pending_span',
                    'logfire.msg': 'GET /',
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
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
                    'code.filepath': 'test_flask.py',
                    'code.function': 'homepage',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'GET /',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'localhost',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'net.host.name': 'localhost',
                    'server.address': 'localhost',
                    'net.host.port': 80,
                    'http.host': 'localhost',
                    'server.port': 80,
                    'http.target': '/',
                    'url.path': '/',
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.route': '/',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'outside request handler',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_flask.py',
                    'code.function': 'test_flask_instrumentation',
                    'code.lineno': 123,
                    'logfire.msg_template': 'outside request handler',
                    'logfire.msg': 'outside request handler',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.flask': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.flask)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_flask()` requires the `opentelemetry-instrumentation-flask` package.
You can install this with:
    pip install 'logfire[flask]'\
""")
