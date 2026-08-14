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

from inline_snapshot import snapshot
from litestar import Litestar, Request, WebSocket, asgi, get, post, websocket
from litestar.params import Parameter
from litestar.testing import TestClient
from opentelemetry.metrics import MeterProvider
from opentelemetry.trace import Span, TracerProvider

import logfire
import logfire.integrations.litestar as public_litestar
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


@asgi(['/mounted', '/other'], is_mount=True, copy_scope=True)
async def mounted(scope: Any, receive: Any, send: Any) -> None:
    pass


@websocket('/chat')
async def chat(socket: WebSocket[Any, Any, Any]) -> None:
    await socket.accept()


def make_app(**instrument_kwargs: Any) -> Litestar:
    return Litestar(route_handlers=[user, health, echo], plugins=[logfire.instrument_litestar(**instrument_kwargs)])


@pytest.fixture(autouse=True)
def restore_header_capture_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST', raising=False)
    monkeypatch.delenv('OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE', raising=False)


def test_routes(exporter: TestExporter) -> None:
    with TestClient(make_app()) as client:
        assert client.get('/users/1').status_code == 200
        assert client.get('/health').status_code == 200

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /users/{user_id}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /users/1',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver.local',
                    'server.address': 'testserver.local',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/users/1',
                    'url.path': '/users/1',
                    'http.url': 'http://testserver.local/users/1',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver.local',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/users/{user_id}',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'GET /health',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver.local',
                    'server.address': 'testserver.local',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/health',
                    'url.path': '/health',
                    'http.url': 'http://testserver.local/health',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver.local',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/health',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
        ]
    )


def test_missing_route_has_method_only(exporter: TestExporter) -> None:
    with TestClient(make_app()) as client:
        assert client.get('/missing').status_code == 404

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /missing',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver.local',
                    'server.address': 'testserver.local',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/missing',
                    'url.path': '/missing',
                    'http.url': 'http://testserver.local/missing',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver.local',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.status_code': 404,
                    'http.response.status_code': 404,
                    'logfire.level_num': 13,
                },
            }
        ]
    )


def test_root_path_is_included_in_canonical_route(exporter: TestExporter) -> None:
    with TestClient(make_app(), root_path='/api') as client:
        assert client.get('/api/users/1').status_code == 200

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /api/users/{user_id}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /api/users/1',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver.local',
                    'server.address': 'testserver.local',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/api/users/1',
                    'url.path': '/api/users/1',
                    'http.url': 'http://testserver.local/api/users/1',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver.local',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/api/users/{user_id}',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            }
        ]
    )


def test_mounted_app_uses_canonical_mount_route() -> None:
    plugin = cast(OpenTelemetryPlugin, logfire.instrument_litestar())
    app = Litestar(route_handlers=[mounted])

    assert plugin.config.scope_span_details_extractor(
        {'app': app, 'method': 'GET', 'path': '/mounted/attacker-controlled'}
    ) == ('GET /mounted', {'http.route': '/mounted'})


def test_websocket_route_has_no_leading_space() -> None:
    plugin = cast(OpenTelemetryPlugin, logfire.instrument_litestar())
    app = Litestar(route_handlers=[chat])

    assert plugin.config.scope_span_details_extractor({'app': app, 'type': 'websocket', 'path': '/chat'}) == (
        '/chat',
        {'http.route': '/chat'},
    )


def test_public_types_module() -> None:
    assert public_litestar.ServerRequestHook is not None
    assert public_litestar.ClientRequestHook is not None
    assert public_litestar.ClientResponseHook is not None


def test_legacy_plugin_namespace() -> None:
    plugin_module = mock.MagicMock()

    def find_spec(name: str) -> object | None:
        return None if name == 'litestar.plugins' else object()

    with (
        mock.patch('importlib.util.find_spec', side_effect=find_spec),
        mock.patch('importlib.import_module', return_value=plugin_module) as import_module,
    ):
        assert logfire.instrument_litestar() is plugin_module.OpenTelemetryPlugin.return_value

    import_module.assert_called_once_with('litestar.contrib.opentelemetry')


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
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'POST /echo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST /echo',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver.local',
                    'server.address': 'testserver.local',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/echo',
                    'url.path': '/echo',
                    'http.url': 'http://testserver.local/echo',
                    'http.method': 'POST',
                    'http.request.method': 'POST',
                    'http.server_name': 'testserver.local',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/echo',
                    'http.status_code': 201,
                    'http.response.status_code': 201,
                },
            }
        ]
    )


def test_record_send_receive_default(exporter: TestExporter) -> None:
    with TestClient(make_app()) as client:
        assert client.get('/health').status_code == 200

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /health',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver.local',
                    'server.address': 'testserver.local',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/health',
                    'url.path': '/health',
                    'http.url': 'http://testserver.local/health',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver.local',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/health',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            }
        ]
    )


def test_record_send_receive_enabled(exporter: TestExporter) -> None:
    with TestClient(make_app(record_send_receive=True)) as client:
        assert client.get('/health').status_code == 200

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /health http send response.start',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.level_num': 5,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health http send response.start',
                    'asgi.event.type': 'http.response.start',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'GET /health http send response.body',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.level_num': 5,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health http send response.body',
                    'asgi.event.type': 'http.response.body',
                },
            },
            {
                'name': 'GET /health',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver.local',
                    'server.address': 'testserver.local',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/health',
                    'url.path': '/health',
                    'http.url': 'http://testserver.local/health',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver.local',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/health',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
        ]
    )


def test_capture_headers(exporter: TestExporter) -> None:
    with TestClient(make_app(capture_headers=True)) as client:
        assert client.get('/health', headers={'x-test-header': 'value'}).status_code == 200

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /health',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver.local',
                    'server.address': 'testserver.local',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/health',
                    'url.path': '/health',
                    'http.url': 'http://testserver.local/health',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver.local',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/health',
                    'http.request.header.host': ('testserver.local',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept_encoding': ('gzip, deflate, zstd',),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user_agent': ('testclient',),
                    'http.request.header.x_test_header': ('value',),
                    'http.response.header.content_type': ('application/json',),
                    'http.response.header.content_length': ('15',),
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            }
        ]
    )
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
