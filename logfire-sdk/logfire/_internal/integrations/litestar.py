from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

try:
    from litestar import Litestar
    from litestar.exceptions import HTTPException
    from litestar.handlers import ASGIRouteHandler
    from litestar.routes import ASGIRoute
    from litestar.utils import normalize_path

    from .asgi import instrument_asgi
except ImportError as exc:
    raise RuntimeError(
        '`logfire.instrument_litestar()` requires Litestar and its OpenTelemetry dependencies.\n'
        'You can install them with:\n'
        "    pip install 'logfire[litestar]'"
    ) from exc

if TYPE_CHECKING:
    from typing_extensions import Unpack

    from logfire import Logfire

    from .asgi import ASGIApp, ASGIInstrumentKwargs


def instrument_litestar(
    logfire_instance: Logfire,
    app: Litestar,
    *,
    record_send_receive: bool = False,
    capture_headers: bool = False,
    **kwargs: Unpack[ASGIInstrumentKwargs],
) -> ASGIApp:
    """Wrap a Litestar app with OpenTelemetry middleware configured for Logfire."""

    def default_span_details(scope: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        method = str(scope.get('method', '')).strip()
        path = str(scope.get('path', ''))
        root_path = str(scope.get('root_path', '')).rstrip('/')
        if root_path and (path == root_path or path.startswith(f'{root_path}/')):
            path = path[len(root_path) :] or '/'
        path = normalize_path(path)
        try:
            routing_result = app.asgi_router.handle_routing(path=path, method=method or None)
        except HTTPException:  # Litestar uses HTTP exceptions to represent 404s and method mismatches.
            return method, {}

        path_template = routing_result[-1]
        route_handler = routing_result[1]
        if not path_template and isinstance(route_handler, ASGIRouteHandler) and route_handler.is_mount:
            mount_paths = (
                route.path
                for route in app.routes
                if isinstance(route, ASGIRoute)
                and route.route_handler is route_handler
                and (path == route.path or path.startswith(f'{route.path.rstrip("/")}/'))
            )
            path_template = max(mount_paths, key=len, default='/')
        path_template = path_template or path
        path_template = '/' + str(path_template).lstrip('/')
        route = f'{root_path}{path_template}'
        span_name = f'{method} {route}' if method else route
        return span_name, {'http.route': route}

    kwargs.setdefault('default_span_details', default_span_details)
    return instrument_asgi(
        logfire_instance,
        cast('ASGIApp', app),
        record_send_receive=record_send_receive,
        capture_headers=capture_headers,
        **kwargs,
    )
