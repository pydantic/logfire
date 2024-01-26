from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, ContextManager, Literal

import fastapi.routing
from fastapi import FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.semconv.trace import SpanAttributes
from starlette.requests import Request
from starlette.websockets import WebSocket

from logfire import Logfire


def instrument_fastapi(
    logfire: Logfire,
    app: FastAPI,
    *,
    attributes_mapper: Callable[
        [
            Request | WebSocket,
            dict[str, Any],
        ],
        dict[str, Any] | None,
    ]
    | None = None,
    use_opentelemetry_instrumentation: bool = True,
) -> ContextManager[None]:
    """Instrument a FastAPI app so that spans and logs are automatically created for each request.

    See `Logfire.instrument_fastapi` for more details.
    """
    logfire = logfire.with_tags('fastapi')
    attributes_mapper = attributes_mapper or _default_attributes_mapper

    if use_opentelemetry_instrumentation:
        FastAPIInstrumentor.instrument_app(app)  # type: ignore

    # It's conceivable that the user might call this function multiple times,
    # and revert some of those calls with the context manager,
    # in which case restoring the old function could go poorly.
    # So instead we keep the patch and just set this boolean.
    # The downside is that performance will suffer if this is called a large number of times.
    instrumenting = True

    async def patched_solve_dependencies(*, request: Request | WebSocket, **kwargs: Any):
        result = await original_solve_dependencies(request=request, **kwargs)
        if not instrumenting or request.app != app:
            return result

        attributes: dict[str, Any] | None = {
            # Shallow copy these so that the user can safely modify them, but we don't tell them that.
            # We do explicitly tell them that the contents should not be modified.
            # Making a deep copy could be very expensive and maybe even impossible.
            'values': result[0].copy(),
            'errors': result[1].copy(),
        }

        attributes = attributes_mapper(request, attributes)
        if not attributes:
            # The user can return None to indicate that they don't want to log anything.
            # We don't document it, but returning `False`, `{}` etc. seems like it should also work.
            return result

        # attributes_mapper may have removed the errors, so we need .get() here.
        level: Literal['error', 'debug'] = 'error' if attributes.get('errors') else 'debug'

        # Add a few basic attributes about the request, particularly so that the user can group logs by endpoint.
        # Usually this will all be inside a span added by FastAPIInstrumentor with more detailed attributes.
        # We only add these attributes after the attributes_mapper so that the user
        # doesn't rely on what we add here - they can use `request` instead.
        if isinstance(request, Request):
            attributes[SpanAttributes.HTTP_METHOD] = request.method
        route: APIRoute | APIWebSocketRoute | None = request.scope.get('route')
        if route:
            attributes.update(
                {
                    SpanAttributes.HTTP_ROUTE: route.path,
                    'fastapi.route.name': route.name,
                }
            )
            if isinstance(route, APIRoute):
                attributes['fastapi.route.operation_id'] = route.operation_id

        logfire.log(level, 'FastAPI arguments', attributes=attributes)
        return result

    # `solve_dependencies` is actually defined in `fastapi.dependencies.utils`,
    # but it's imported into `fastapi.routing`, which is where we need to patch it.
    # It also calls itself recursively, but for now we don't want to intercept those calls,
    # so we don't patch it back into the original module.
    original_solve_dependencies = fastapi.routing.solve_dependencies  # type: ignore
    fastapi.routing.solve_dependencies = patched_solve_dependencies  # type: ignore

    @contextmanager
    def uninstrument_context():
        # The user isn't required (or even expected) to use this context manager,
        # which is why the instrumenting and patching has already happened before this point.
        # It exists mostly for tests, and just in case users want it.
        nonlocal instrumenting
        try:
            yield
        finally:
            instrumenting = False
            FastAPIInstrumentor.uninstrument_app(app)

    return uninstrument_context()


def _default_attributes_mapper(
    _request: Request | WebSocket,
    attributes: dict[str, Any],
):
    return attributes
