from __future__ import annotations

import inspect
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Awaitable, Callable, ContextManager, Iterable, cast
from weakref import WeakKeyDictionary

import fastapi.routing
from fastapi import BackgroundTasks, FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.security import SecurityScopes
from starlette.requests import Request
from starlette.responses import Response
from starlette.websockets import WebSocket

from ..main import Logfire
from ..stack_info import StackInfo, get_code_object_info

try:
    from opentelemetry.instrumentation.asgi import get_host_port_url_tuple  # type: ignore
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.semconv.trace import SpanAttributes
    from opentelemetry.util.http import get_excluded_urls, parse_excluded_urls
except ModuleNotFoundError:
    raise RuntimeError(
        'The `logfire.instrument_fastapi()` requires the `opentelemetry-instrumentation-fastapi` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[fastapi]'"
    )


def instrument_fastapi(
    logfire_instance: Logfire,
    app: FastAPI,
    *,
    request_attributes_mapper: Callable[
        [
            Request | WebSocket,
            dict[str, Any],
        ],
        dict[str, Any] | None,
    ]
    | None = None,
    use_opentelemetry_instrumentation: bool = True,
    excluded_urls: str | Iterable[str] | None = None,
    **opentelemetry_kwargs: Any,
) -> ContextManager[None]:
    """Instrument a FastAPI app so that spans and logs are automatically created for each request.

    See `Logfire.instrument_fastapi` for more details.
    """
    # TODO(Marcelo): This needs to be tested.
    if not isinstance(excluded_urls, (str, type(None))):  # pragma: no cover
        # FastAPIInstrumentor expects a comma-separated string, not a list.
        excluded_urls = ','.join(excluded_urls)

    if use_opentelemetry_instrumentation:  # pragma: no branch
        FastAPIInstrumentor.instrument_app(app, excluded_urls=excluded_urls, **opentelemetry_kwargs)  # type: ignore

    registry = patch_fastapi()
    if app in registry:  # pragma: no cover
        raise ValueError('This app has already been instrumented.')

    registry[app] = FastAPIInstrumentation(
        logfire_instance,
        request_attributes_mapper or _default_request_attributes_mapper,
        excluded_urls,
    )

    @contextmanager
    def uninstrument_context():
        # The user isn't required (or even expected) to use this context manager,
        # which is why the instrumenting and patching has already happened before this point.
        # It exists mostly for tests, and just in case users want it.
        try:
            yield
        finally:
            del registry[app]
            if use_opentelemetry_instrumentation:  # pragma: no branch
                FastAPIInstrumentor.uninstrument_app(app)

    return uninstrument_context()


@lru_cache  # only patch once
def patch_fastapi():
    """Globally monkeypatch fastapi functions and return a dictionary for recording instrumentation config per app."""
    registry: WeakKeyDictionary[FastAPI, FastAPIInstrumentation] = WeakKeyDictionary()

    async def patched_solve_dependencies(*, request: Request | WebSocket, **kwargs: Any):
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
        excluded_urls: str | None,
    ):
        self.logfire_instance = logfire_instance.with_tags('fastapi')
        self.request_attributes_mapper = request_attributes_mapper

        # These lines, as well as the `excluded_urls_list.url_disabled` call below, are copied from OTEL.
        if excluded_urls is None:
            self.excluded_urls_list = get_excluded_urls('FASTAPI')
        else:
            self.excluded_urls_list = parse_excluded_urls(excluded_urls)  # pragma: no cover

    async def solve_dependencies(
        self, request: Request | WebSocket, original: Awaitable[tuple[dict[str, Any], list[Any], Any, Any, Any]]
    ):
        try:
            url = cast(str, get_host_port_url_tuple(request.scope)[2])
            excluded = self.excluded_urls_list.url_disabled(url)
        except Exception:  # pragma: no cover
            excluded = False
            self.logfire_instance.exception('Error checking if URL is excluded from instrumentation')

        if excluded:
            return await original  # pragma: no cover

        with self.logfire_instance.span('FastAPI arguments') as span:
            result = await original

            try:
                attributes: dict[str, Any] | None = {
                    # Shallow copy these so that the user can safely modify them, but we don't tell them that.
                    # We do explicitly tell them that the contents should not be modified.
                    # Making a deep copy could be very expensive and maybe even impossible.
                    'values': {
                        k: v
                        for k, v in result[0].items()
                        if not isinstance(v, (Request, WebSocket, BackgroundTasks, SecurityScopes, Response))
                    },
                    'errors': result[1].copy(),
                }

                # Set the current app on `values` so that `patched_run_endpoint_function` can check it.
                if isinstance(request, Request):  # pragma: no branch
                    instrumented_values = _InstrumentedValues(result[0])
                    instrumented_values.request = request
                    result = (instrumented_values, *result[1:])

                attributes = self.request_attributes_mapper(request, attributes)
                if not attributes:
                    # The user can return None to indicate that they don't want to log anything.
                    # We don't document it, but returning `False`, `{}` etc. seems like it should also work.
                    # We can't drop the span since it's already been created,
                    # but we can set the level to debug so that it's hidden by default.
                    span.set_level('debug')
                    return result

                # request_attributes_mapper may have removed the errors, so we need .get() here.
                if attributes.get('errors'):
                    span.set_level('error')

                # Add a few basic attributes about the request, particularly so that the user can group logs by endpoint.
                # Usually this will all be inside a span added by FastAPIInstrumentor with more detailed attributes.
                # We only add these attributes after the request_attributes_mapper so that the user
                # doesn't rely on what we add here - they can use `request` instead.
                if isinstance(request, Request):  # pragma: no branch
                    attributes[SpanAttributes.HTTP_METHOD] = request.method
                route: APIRoute | APIWebSocketRoute | None = request.scope.get('route')
                if route:  # pragma: no branch
                    attributes.update(
                        {
                            SpanAttributes.HTTP_ROUTE: route.path,
                            'fastapi.route.name': route.name,
                        }
                    )
                    if isinstance(route, APIRoute):  # pragma: no branch
                        attributes['fastapi.route.operation_id'] = route.operation_id

                span.set_attributes(attributes)
            except Exception as e:  # pragma: no cover
                span.record_exception(e)

        return result

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
