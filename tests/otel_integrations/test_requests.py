from __future__ import annotations

import importlib
from typing import Any
from unittest import mock

import pytest
import requests
from inline_snapshot import snapshot
from opentelemetry.instrumentation.requests import RequestsInstrumentor

import logfire
import logfire._internal.integrations.requests
from logfire.testing import TestExporter


@pytest.fixture(autouse=True)  # only applies within this module
def instrument_requests(monkeypatch: pytest.MonkeyPatch):
    # The following monkeypatching is similar in purpose to the mock transport in test_httpx.py.

    def send(self: Any, request: requests.Request, **kwargs: Any):
        response = requests.Response()
        response.status_code = 200
        response.headers = request.headers
        return response

    monkeypatch.setattr(requests.Session, 'send', send)

    logfire.instrument_requests()
    yield
    instrumentor = RequestsInstrumentor()
    instrumentor.uninstrument()


@pytest.mark.anyio
async def test_requests_instrumentation(exporter: TestExporter):
    with logfire.span('test span') as span:
        assert span.context
        trace_id = span.context.trace_id
        response = requests.get('https://example.org:8080/foo')
        # Validation of context propagation: ensure that the traceparent header contains the trace ID
        traceparent_header = response.headers['traceparent']
        assert f'{trace_id:032x}' == traceparent_header.split('-')[1]

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.url': 'https://example.org:8080/foo',
                    'url.full': 'https://example.org:8080/foo',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'net.peer.port': 8080,
                    'server.port': 8080,
                    'network.peer.port': 8080,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET example.org/foo',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.target': '/foo',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_requests.py',
                    'code.lineno': 123,
                    'code.function': 'test_requests_instrumentation',
                    'logfire.msg_template': 'test span',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test span',
                },
            },
        ]
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.requests': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.requests)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_requests()` requires the `opentelemetry-instrumentation-requests` package.
You can install this with:
    pip install 'logfire[requests]'\
""")
