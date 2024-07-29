from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

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


def instrument_httpx(**kwargs: Unpack[HTTPXInstrumentKwargs]) -> None:
    """Instrument the `httpx` module so that spans are automatically created for each request.

    See the `Logfire.instrument_httpx` method for details.
    """
    HTTPXClientInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
