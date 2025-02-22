from __future__ import annotations

import dataclasses
import inspect
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Awaitable, Callable, ContextManager, Iterable
from weakref import WeakKeyDictionary

import fastapi.routing
from fastapi import BackgroundTasks, FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute, Mount
from fastapi.security import SecurityScopes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Span
from starlette.requests import Request
from starlette.responses import Response
from starlette.websockets import WebSocket

from ..main import Logfire, set_user_attributes_on_raw_span
from ..stack_info import StackInfo, get_code_object_info
from ..utils import handle_internal_errors, maybe_capture_server_headers
from .asgi import tweak_asgi_spans_tracer_provider

try:
    from opentelemetry.instrumentation.asgi import ServerRequestHook
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
except ImportError:
    raise RuntimeError(
        'The `logfire.instrument_fastapi()` requires the `opentelemetry-instrumentation-fastapi` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[fastapi]'"
    )


def find_mounted_apps(app: FastAPI) -> list[FastAPI]:
    """Fetch all sub-apps mounted to a FastAPI app, including nested sub-apps."""
    mounted_apps: list[FastAPI] = []
    for route in app.routes:
        if isinstance(route, Mount):
            _app: Any = route.app
            if isinstance(_app, FastAPI):
                mounted_apps.append(_app)
                mounted_apps += find_mounted_apps(_app)
    return mounted_apps


def instrument_fastapi(
    logfire_instance: Logfire,
    app: FastAPI,
    *,
    capture_headers: bool = False,
    request_attributes_mapper: Callable[
        [
            Request | WebSocket,
            dict[str, Any],
        ],
        dict[str, Any] | None,
    ]
    | None = None,
    excluded_urls: str | Iterable[str] | None = None,
    record_send_receive: bool = False,
    **opentelemetry_kwargs: Any,
) -> ContextManager[None]:
    """Instrument a FastAPI app so that spans and logs are automatically created for each request.

    See `Logfire.instrument_fastapi` for more details.
    """
    # TODO(Marcelo): This needs to be tested.
    if not isinstance(excluded_urls, (str, type(None))):  # pragma: no cover
        # FastAPIInstrumentor expects a comma-separated string, not a list.
        excluded_urls = ','.join(excluded_urls)

    maybe_capture_server_headers(capture_headers)
    opentelemetry_kwargs = {
        'tracer_provider': tweak_asgi_spans_tracer_provider(logfire_instance, record_send_receive),
        'meter_provider': logfire_instance.config.get_meter_provider(),
        **opentelemetry_kwargs,
    }
    FastAPIInstrumentor.instrument_app(  # type: ignore
        app,
        excluded_urls=excluded_urls,
        server_request_hook=_server_request_hook(opentelemetry_kwargs.pop('server_request_hook', None)),
        **opentelemetry_kwargs,
    )

    registry = patch_fastapi()
    if app in registry:  # pragma: no cover
        raise ValueError('This app has already been instrumented.')

    mounted_apps = find_mounted_apps(app)
    mounted_apps.append(app)

    for _app in mounted_apps:
        registry[_app] = FastAPIInstrumentation(
            logfire_instance,
            request_attributes_mapper or _default_request_attributes_mapper,
        )

    @contextmanager
    def uninstrument_context():
        # The user isn't required (or even expected) to use this context manager,
        # which is why the instrumenting and patching has already happened before this point.
        # It exists mostly for tests, and just in case users want it.
        try:
            yield
        finally:
            for _app in mounted_apps:
                del registry[_app]
                FastAPIInstrumentor.uninstrument_app(_app)

    return uninstrument_context()


@lru_cache  # only patch once
def patch_fastapi():
    """Globally monkeypatch fastapi functions and return a dictionary for recording instrumentation config per app."""
    registry: WeakKeyDictionary[FastAPI, FastAPIInstrumentation] = WeakKeyDictionary()

    async def patched_solve_dependencies(*, request: Request | WebSocket, **kwargs: Any) -> Any:
        original = original_solve_dependencies(request=request, **kwargs)
        if instrumentation := registry.get(request.app):
            return await instrumentation.solve_dependencies(request, original)
        else:
            return await original  # pragma: no cover

    # `solve_dependencies` is actually defined in `fastapi.dependencies.utils`,
    # but it's imported into `fastapi.routing`, which is where we need to patch it.
    # It also calls itself recursively, but for now we don't want to intercept those calls,
    # so we don't patch it back into the original module.
    original_solve_dependencies = fastapi.routing.solve_dependencies  # type: ignore
    fastapi.routing.solve_dependencies = patched_solve_dependencies  # type: ignore

    async def patched_run_endpoint_function(*, dependant: Any, values: dict[str, Any], **kwargs: Any) -> Any:
        if isinstance(values, _InstrumentedValues):
            request = values.request
            if instrumentation := registry.get(request.app):  # pragma: no branch
                return await instrumentation.run_endpoint_function(
                    original_run_endpoint_function, request, dependant, values, **kwargs
                )
        return await original_run_endpoint_function(dependant=dependant, values=values, **kwargs)  # pragma: no cover

    original_run_endpoint_function = fastapi.routing.run_endpoint_function
    fastapi.routing.run_endpoint_function = patched_run_endpoint_function

    return registry


class FastAPIInstrumentation:
    def __init__(
        self,
        logfire_instance: Logfire,
        request_attributes_mapper: Callable[
            [
                Request | WebSocket,
                dict[str, Any],
            ],
            dict[str, Any] | None,
        ],
    ):
        self.logfire_instance = logfire_instance.with_settings(custom_scope_suffix='fastapi')
        self.request_attributes_mapper = request_attributes_mapper

    async def solve_dependencies(self, request: Request | WebSocket, original: Awaitable[Any]) -> Any:
        root_span = request.scope.get(LOGFIRE_SPAN_SCOPE_KEY)
        if not (root_span and root_span.is_recording()):
            return await original

        with self.logfire_instance.span('FastAPI arguments') as span:
            with handle_internal_errors:
                if isinstance(request, Request):  # pragma: no branch
                    span.set_attribute(SpanAttributes.HTTP_METHOD, request.method)
                route: APIRoute | APIWebSocketRoute | None = request.scope.get('route')
                if route:  # pragma: no branch
                    span.set_attribute(SpanAttributes.HTTP_ROUTE, route.path)
                    fastapi_route_attributes: dict[str, Any] = {'fastapi.route.name': route.name}
                    if isinstance(route, APIRoute):  # pragma: no branch
                        fastapi_route_attributes['fastapi.route.operation_id'] = route.operation_id
                    set_user_attributes_on_raw_span(root_span, fastapi_route_attributes)
                    span.set_attributes(fastapi_route_attributes)

            result: Any = await original

            with handle_internal_errors:
                solved_values: dict[str, Any]
                solved_errors: list[Any]

                if isinstance(result, tuple):  # pragma: no cover
                    solved_values = result[0]  # type: ignore
                    solved_errors = result[1]  # type: ignore

                    def solved_with_new_values(new_values: dict[str, Any]) -> Any:
                        return new_values, *result[1:]
                else:
                    solved_values = result.values
                    solved_errors = result.errors

                    def solved_with_new_values(new_values: dict[str, Any]) -> Any:
                        return dataclasses.replace(result, values=new_values)

                attributes: dict[str, Any] | None = {
                    # Shallow copy these so that the user can safely modify them, but we don't tell them that.
                    # We do explicitly tell them that the contents should not be modified.
                    # Making a deep copy could be very expensive and maybe even impossible.
                    'values': {
                        k: v
                        for k, v in solved_values.items()  # type: ignore
                        if not isinstance(v, (Request, WebSocket, BackgroundTasks, SecurityScopes, Response))
                    },
                    'errors': solved_errors.copy(),  # type: ignore
                }

                # Set the current app on `values` so that `patched_run_endpoint_function` can check it.
                if isinstance(request, Request):  # pragma: no branch
                    instrumented_values = _InstrumentedValues(solved_values)
                    instrumented_values.request = request
                    result: Any = solved_with_new_values(instrumented_values)

                attributes = self.request_attributes_mapper(request, attributes)
                if not attributes:
                    # The user can return None to indicate that they don't want to log anything.
                    # We don't document it, but returning `False`, `{}` etc. seems like it should also work.
                    # We can't drop the span since it's already been created,
                    # but we can set the level to debug so that it's hidden by default.
                    span.set_level('debug')
                    return result  # type: ignore

                # request_attributes_mapper may have removed the errors, so we need .get() here.
                if attributes.get('errors'):
                    span.set_level('error')

                span.set_attributes(attributes)
                for key in ('values', 'errors'):
                    if key in attributes:  # pragma: no branch
                        attributes['fastapi.arguments.' + key] = attributes.pop(key)
                set_user_attributes_on_raw_span(root_span, attributes)

        return result  # type: ignore

    async def run_endpoint_function(
        self,
        original_run_endpoint_function: Any,
        request: Request,
        dependant: Any,
        values: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        callback = inspect.unwrap(dependant.call)
        code = getattr(callback, '__code__', None)
        stack_info: StackInfo = get_code_object_info(code) if code else {}
        with self.logfire_instance.span(
            '{method} {http.route} ({code.function})',
            method=request.method,
            # Using `http.route` prevents it from being scrubbed if it contains a word like 'secret'.
            # We don't use `http.method` because some dashboards do things like count spans with
            # both `http.method` and `http.route`.
            **{'http.route': request.scope['route'].path},
            **stack_info,
            _level='debug',
        ):
            return await original_run_endpoint_function(dependant=dependant, values=values, **kwargs)


def _default_request_attributes_mapper(
    _request: Request | WebSocket,
    attributes: dict[str, Any],
):
    return attributes  # pragma: no cover


class _InstrumentedValues(dict):  # type: ignore
    request: Request


LOGFIRE_SPAN_SCOPE_KEY = 'logfire.span'


def _server_request_hook(user_hook: ServerRequestHook | None):
    # Add the span to the request scope so that we can access it in `solve_dependencies`.
    # Also call the user's hook if they passed one.
    def hook(span: Span, scope: dict[str, Any]):
        scope[LOGFIRE_SPAN_SCOPE_KEY] = span
        if user_hook:
            user_hook(span, scope)

    return hook
