from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Awaitable, Callable

try:
    from opentelemetry.instrumentation.httpx import (
        AsyncRequestHook,
        AsyncResponseHook,
        HTTPXClientInstrumentor,
        RequestHook,
        RequestInfo,
        ResponseHook,
        ResponseInfo,
    )
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_httpx()` requires the `opentelemetry-instrumentation-httpx` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[httpx]'"
    )

from logfire import Logfire

if TYPE_CHECKING:
    from typing import TypedDict, TypeVar, Unpack

    import httpx
    from opentelemetry.trace import Span

    class HTTPXInstrumentKwargs(TypedDict, total=False):
        request_hook: RequestHook
        response_hook: ResponseHook
        async_request_hook: AsyncRequestHook
        async_response_hook: AsyncResponseHook
        skip_dep_check: bool

    Info = TypeVar('Info', RequestInfo, ResponseInfo)


def instrument_httpx(
    logfire_instance: Logfire,
    client: httpx.Client | httpx.AsyncClient | None,
    capture_request_headers: bool,
    capture_response_headers: bool,
    **kwargs: Unpack[HTTPXInstrumentKwargs],
) -> None:
    """Instrument the `httpx` module so that spans are automatically created for each request.

    See the `Logfire.instrument_httpx` method for details.
    """
    final_kwargs: dict[str, Any] = {
        'tracer_provider': logfire_instance.config.get_tracer_provider(),
        'meter_provider': logfire_instance.config.get_meter_provider(),
        **kwargs,
    }
    capture_headers = dict(request=capture_request_headers, response=capture_response_headers)
    for request_or_response, capture in capture_headers.items():
        if capture:
            for kwarg_name in [f'{request_or_response}_hook', f'async_{request_or_response}_hook']:
                kwarg = final_kwargs.get(kwarg_name)
                is_async = kwarg_name.startswith('async_') or inspect.iscoroutinefunction(kwarg)
                maker = make_capture_headers_async_hook if is_async else make_capture_headers_hook
                final_kwargs[kwarg_name] = maker(kwarg, request_or_response)

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
        instrumentor.instrument(**final_kwargs)


def make_capture_headers_hook(
    hook: Callable[[Span, Info], None] | None,
    request_or_response: str,
) -> Callable[[Span, Info], None]:
    def capture_headers_hook(span: Span, info: Info) -> None:
        capture_headers(span, info.headers, request_or_response)
        if hook:
            hook(span, info)

    return capture_headers_hook


def make_capture_headers_async_hook(
    hook: Callable[[Span, Info], Awaitable[None]] | None,
    request_or_response: str,
) -> Callable[[Span, Info], Awaitable[None]]:
    async def capture_headers_hook(span: Span, info: Info) -> None:
        capture_headers(span, info.headers, request_or_response)
        if hook:
            result = hook(span, info)
            while inspect.isawaitable(result):
                result = await result

    return capture_headers_hook


def capture_headers(span: Span, headers: Any, request_or_response: str) -> None:
    span.set_attributes(
        {
            f'http.{request_or_response}.header.{header_name}': headers.get_list(header_name)
            for header_name in headers.keys()
        }
    )
