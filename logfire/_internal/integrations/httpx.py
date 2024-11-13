from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
except ModuleNotFoundError:
    raise RuntimeError(
        '`logfire.instrument_httpx()` requires the `opentelemetry-instrumentation-httpx` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[httpx]'"
    )

from logfire import Logfire

if TYPE_CHECKING:
    from typing import Awaitable, Callable, TypedDict, Unpack

    import httpx
    from opentelemetry.trace import Span

    RequestHook = Callable[[Span, httpx.Request], None]
    ResponseHook = Callable[[Span, httpx.Request, httpx.Response], None]
    AsyncRequestHook = Callable[[Span, httpx.Request], Awaitable[None]]
    AsyncResponseHook = Callable[[Span, httpx.Request, httpx.Response], Awaitable[None]]

    class HTTPXInstrumentKwargs(TypedDict, total=False):
        request_hook: RequestHook
        response_hook: ResponseHook
        async_request_hook: AsyncRequestHook
        async_response_hook: AsyncResponseHook
        skip_dep_check: bool


def instrument_httpx(
    logfire_instance: Logfire, client: httpx.Client | httpx.AsyncClient | None, **kwargs: Unpack[HTTPXInstrumentKwargs]
) -> None:
    """Instrument the `httpx` module so that spans are automatically created for each request.

    See the `Logfire.instrument_httpx` method for details.
    """
    final_kwargs: dict[str, Any] = {
        'tracer_provider': logfire_instance.config.get_tracer_provider(),
        'meter_provider': logfire_instance.config.get_meter_provider(),
        **kwargs,
    }
    del kwargs  # make sure only final_kwargs is used
    instrumentor = HTTPXClientInstrumentor()
    if client:
        instrumentor.instrument_client(
            client,
            tracer_provider=final_kwargs['tracer_provider'],
            request_hook=final_kwargs.get('request_hook'),
            response_hook=final_kwargs.get('response_hook'),
        )
    else:
        instrumentor.instrument(**final_kwargs)  # type: ignore[reportUnknownMemberType]
