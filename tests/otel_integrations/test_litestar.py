from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable
from typing import Annotated, Any, Protocol, cast
from unittest import mock

import pytest

pytest.importorskip(
    'pydantic',
    minversion='2.5',
    reason='Litestar 2.11 and later require Pydantic 2.5 or later.',
)

from litestar import Litestar, Request, get, post
from litestar.params import Parameter
from litestar.testing import TestClient
from opentelemetry.metrics import MeterProvider
from opentelemetry.trace import Span, TracerProvider

import logfire
from logfire.testing import TestExporter


class OpenTelemetryConfig(Protocol):
    scope_span_details_extractor: Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]
    meter_provider: MeterProvider | None
    tracer_provider: TracerProvider | None
    server_request_hook_handler: Callable[[Span, dict[str, Any]], None] | None


class OpenTelemetryPlugin(Protocol):
    config: OpenTelemetryConfig


@get('/users/{user_id:int}')
async def user(user_id: Annotated[int, Parameter()]) -> dict[str, int]:
    return {'user_id': user_id}


@get('/health')
async def health() -> dict[str, str]:
    return {'status': 'ok'}


@post('/echo')
async def echo(request: Request[Any, Any, Any]) -> dict[str, str]:
    return {'body': (await request.body()).decode()}


def make_app(**instrument_kwargs: Any) -> Litestar:
    return Litestar(route_handlers=[user, health, echo], plugins=[logfire.instrument_litestar(**instrument_kwargs)])


def server_spans(exporter: TestExporter) -> list[dict[str, Any]]:
    return [
        span
        for span in exporter.exported_spans_as_dict(parse_json_attributes=True)
        if span['attributes'].get('logfire.level_num') != 5
    ]


@pytest.fixture(autouse=True)
def restore_header_capture_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST', raising=False)
    monkeypatch.delenv('OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE', raising=False)


@pytest.mark.parametrize(
    ('path', 'expected_name', 'expected_route'),
    [
        ('/users/1', 'GET /users/{user_id}', '/users/{user_id}'),
        ('/health', 'GET /health', '/health'),
    ],
)
def test_routes(path: str, expected_name: str, expected_route: str, exporter: TestExporter) -> None:
    with TestClient(make_app()) as client:
        assert client.get(path).status_code == 200

    [span] = server_spans(exporter)
    assert span['name'] == expected_name
    assert span['attributes']['http.route'] == expected_route


def test_missing_route_has_method_only(exporter: TestExporter) -> None:
    with TestClient(make_app()) as client:
        assert client.get('/missing').status_code == 404

    [span] = server_spans(exporter)
    assert span['name'] == 'GET'
    assert 'http.route' not in span['attributes']


def test_root_path_is_included_in_canonical_route(exporter: TestExporter) -> None:
    with TestClient(make_app(), root_path='/api') as client:
        assert client.get('/api/users/1').status_code == 200

    [span] = server_spans(exporter)
    assert span['name'] == 'GET /api/users/{user_id}'
    assert span['attributes']['http.route'] == '/api/users/{user_id}'


def test_config_defaults_and_overrides() -> None:
    plugin = cast(OpenTelemetryPlugin, logfire.instrument_litestar())
    app = Litestar(route_handlers=[health])
    assert plugin.config.scope_span_details_extractor({'app': app, 'method': 'GET', 'path': '/health'}) == (
        'GET /health',
        {'http.route': '/health'},
    )
    assert plugin.config.meter_provider is logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_meter_provider()

    tracer_provider: TracerProvider = mock.MagicMock(spec=TracerProvider)
    meter_provider: MeterProvider = mock.MagicMock(spec=MeterProvider)

    def span_details(scope: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        return 'custom', {}

    def server_hook(span: Span, scope: dict[str, Any]) -> None:
        pass

    plugin = cast(
        OpenTelemetryPlugin,
        logfire.instrument_litestar(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            scope_span_details_extractor=span_details,
            server_request_hook_handler=server_hook,
        ),
    )
    assert plugin.config.tracer_provider is tracer_provider
    assert plugin.config.meter_provider is meter_provider
    assert plugin.config.scope_span_details_extractor is span_details
    assert plugin.config.server_request_hook_handler is server_hook


def test_hooks_are_forwarded(exporter: TestExporter) -> None:
    calls: list[str] = []

    def server_hook(span: Span, scope: dict[str, Any]) -> None:
        calls.append('server')

    def client_request_hook(span: Span, scope: dict[str, Any], message: dict[str, Any]) -> None:
        calls.append('request')

    def client_response_hook(span: Span, scope: dict[str, Any], message: dict[str, Any]) -> None:
        calls.append('response')

    with TestClient(
        make_app(
            server_request_hook=server_hook,
            client_request_hook=client_request_hook,
            client_response_hook=client_response_hook,
        )
    ) as client:
        assert client.post('/echo', content='test').status_code == 201

    assert calls[0] == 'server'
    assert 'request' in calls
    assert calls.count('response') >= 1
    assert len(server_spans(exporter)) == 1


@pytest.mark.parametrize('record_send_receive', [False, True])
def test_record_send_receive(record_send_receive: bool, exporter: TestExporter) -> None:
    with TestClient(make_app(record_send_receive=record_send_receive)) as client:
        assert client.get('/health').status_code == 200

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    send_receive_spans = [span for span in spans if span['attributes'].get('logfire.level_num') == 5]
    assert bool(send_receive_spans) is record_send_receive
    assert len(server_spans(exporter)) == 1


def test_capture_headers(exporter: TestExporter) -> None:
    with TestClient(make_app(capture_headers=True)) as client:
        assert client.get('/health', headers={'x-test-header': 'value'}).status_code == 200

    [span] = server_spans(exporter)
    assert span['attributes']['http.request.header.x_test_header'] == ('value',)
    assert os.environ['OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST'] == '.*'
    assert os.environ['OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE'] == '.*'


def test_missing_litestar_dependency() -> None:
    real_find_spec = importlib.util.find_spec

    def find_spec(name: str) -> Any:
        return None if name == 'litestar' else real_find_spec(name)

    with mock.patch('importlib.util.find_spec', side_effect=find_spec):
        with pytest.raises(RuntimeError, match=r"pip install 'logfire\[litestar\]'"):
            logfire.instrument_litestar(capture_headers=True)

    assert 'OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST' not in os.environ
    assert 'OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE' not in os.environ


def test_missing_asgi_dependency() -> None:
    missing_asgi = ModuleNotFoundError(
        "No module named 'opentelemetry.instrumentation.asgi'", name='opentelemetry.instrumentation.asgi'
    )
    with mock.patch('importlib.import_module', side_effect=missing_asgi):
        with pytest.raises(RuntimeError, match=r"pip install 'logfire\[litestar\]'"):
            logfire.instrument_litestar(capture_headers=True)

    assert 'OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST' not in os.environ
    assert 'OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE' not in os.environ


def test_unrelated_plugin_import_error_is_not_hidden() -> None:
    unrelated = ModuleNotFoundError("No module named 'unexpected_dependency'", name='unexpected_dependency')
    with mock.patch('importlib.import_module', side_effect=unrelated):
        with pytest.raises(ModuleNotFoundError) as exc_info:
            logfire.instrument_litestar()

    assert exc_info.value is unrelated
