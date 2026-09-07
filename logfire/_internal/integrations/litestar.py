from __future__ import annotations

import importlib
import importlib.util
from dataclasses import fields
from types import ModuleType
from typing import TYPE_CHECKING, Any

from logfire._internal.utils import maybe_capture_server_headers

if TYPE_CHECKING:
    from opentelemetry.instrumentation.asgi.types import ClientRequestHook, ClientResponseHook, ServerRequestHook
    from typing_extensions import Unpack

    from logfire import Logfire
    from logfire.integrations.litestar import LitestarInstrumentKwargs


def _missing_dependency_error() -> RuntimeError:
    return RuntimeError(
        '`logfire.instrument_litestar()` requires Litestar and its OpenTelemetry dependencies.\n'
        'You can install them with:\n'
        "    pip install 'logfire[litestar]'"
    )


def _opentelemetry_module() -> ModuleType:
    """Load Litestar's OpenTelemetry plugin from either supported namespace."""
    if importlib.util.find_spec('litestar') is None:
        raise _missing_dependency_error()
    try:
        if (
            importlib.util.find_spec('litestar.plugins') is not None
            and importlib.util.find_spec('litestar.plugins.opentelemetry') is not None
        ):
            return importlib.import_module('litestar.plugins.opentelemetry')
        return importlib.import_module('litestar.contrib.opentelemetry')
    except ModuleNotFoundError as exc:
        if exc.name == 'opentelemetry.instrumentation.asgi' or (
            exc.name and exc.name.startswith('opentelemetry.instrumentation.asgi.')
        ):
            raise _missing_dependency_error() from exc
        raise


def _route_details(scope: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Resolve a Litestar route before OpenTelemetry creates its server span."""
    from litestar.exceptions import HTTPException
    from litestar.handlers import ASGIRouteHandler
    from litestar.routes import ASGIRoute
    from litestar.utils import normalize_path

    method = str(scope.get('method', '')).strip()
    path = str(scope.get('path', ''))
    root_path = str(scope.get('root_path', '')).rstrip('/')
    if root_path and (path == root_path or path.startswith(f'{root_path}/')):
        path = path[len(root_path) :] or '/'
    path = normalize_path(path)
    try:
        routing_result = scope['app'].asgi_router.handle_routing(path=path, method=method or None)
    except HTTPException:  # Litestar uses HTTP exceptions to represent 404s and method mismatches.
        return method, {}

    path_template = routing_result[-1]
    route_handler = routing_result[1]
    if not path_template and isinstance(route_handler, ASGIRouteHandler) and route_handler.is_mount:
        mount_paths = (
            route.path
            for route in scope['app'].routes
            if isinstance(route, ASGIRoute)
            and route.route_handler is route_handler
            and (path == route.path or path.startswith(f'{route.path.rstrip("/")}/'))
        )
        path_template = max(mount_paths, key=len, default='/')
    path_template = path_template or path
    path_template = '/' + str(path_template).lstrip('/')
    route = f'{root_path}{path_template}' or '/'
    span_name = f'{method} {route}' if method else route
    return span_name, {'http.route': route}


def instrument_litestar(
    logfire_instance: Logfire,
    *,
    record_send_receive: bool = False,
    capture_headers: bool = False,
    server_request_hook: ServerRequestHook | None = None,
    client_request_hook: ClientRequestHook | None = None,
    client_response_hook: ClientResponseHook | None = None,
    **kwargs: Unpack[LitestarInstrumentKwargs],
) -> Any:
    """Return Litestar's OpenTelemetry plugin configured for Logfire."""
    otel = _opentelemetry_module()
    unsupported_options = kwargs.keys() - {field.name for field in fields(otel.OpenTelemetryConfig)}
    if unsupported_options:
        raise RuntimeError(
            'The installed Litestar version does not support these OpenTelemetry options: '
            f'{", ".join(sorted(unsupported_options))}.\n'
            'Upgrade Litestar to use them:\n'
            "    pip install --upgrade 'logfire[litestar]'"
        )

    from logfire._internal.integrations.asgi import tweak_asgi_spans_tracer_provider

    maybe_capture_server_headers(capture_headers)
    kwargs.setdefault('tracer_provider', tweak_asgi_spans_tracer_provider(logfire_instance, record_send_receive))
    kwargs.setdefault('meter_provider', logfire_instance.config.get_meter_provider())
    kwargs.setdefault('scope_span_details_extractor', _route_details)
    kwargs.setdefault('server_request_hook_handler', server_request_hook)
    kwargs.setdefault('client_request_hook_handler', client_request_hook)
    kwargs.setdefault('client_response_hook_handler', client_response_hook)
    config = otel.OpenTelemetryConfig(**kwargs)
    return otel.OpenTelemetryPlugin(config=config)
