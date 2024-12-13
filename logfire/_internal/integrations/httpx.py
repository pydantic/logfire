from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Callable, Literal, cast

import httpx

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
    from typing import ParamSpec, TypedDict, TypeVar, Unpack

    from opentelemetry.trace import Span

    class HTTPXInstrumentKwargs(TypedDict, total=False):
        request_hook: RequestHook
        response_hook: ResponseHook
        async_request_hook: AsyncRequestHook
        async_response_hook: AsyncResponseHook
        skip_dep_check: bool

    Hook = TypeVar('Hook', RequestHook, ResponseHook)
    AsyncHook = TypeVar('AsyncHook', AsyncRequestHook, AsyncResponseHook)

    P = ParamSpec('P')


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

    if capture_request_headers:
        final_kwargs['request_hook'] = make_capture_request_headers_hook(final_kwargs.get('request_hook'))
        final_kwargs['async_request_hook'] = make_capture_async_request_headers_hook(final_kwargs.get('async_request_hook'))  # fmt: skip

    if capture_response_headers:
        final_kwargs['response_hook'] = make_capture_response_headers_hook(final_kwargs.get('response_hook'))
        final_kwargs['async_response_hook'] = make_capture_async_response_headers_hook(final_kwargs.get('async_response_hook'))  # fmt: skip

    del kwargs  # make sure only final_kwargs is used
    instrumentor = HTTPXClientInstrumentor()
    if client:
        hook_prefix = 'async_' if isinstance(client, httpx.AsyncClient) else ''
        request_hook = final_kwargs.get(f'{hook_prefix}request_hook')
        response_hook = final_kwargs.get(f'{hook_prefix}response_hook')

        instrumentor.instrument_client(
            client,
            tracer_provider=final_kwargs['tracer_provider'],
            request_hook=request_hook,
            response_hook=response_hook,
        )
    else:
        instrumentor.instrument(**final_kwargs)


def make_capture_response_headers_hook(hook: ResponseHook | None) -> ResponseHook:
    def capture_response_headers_hook(span: Span, request: RequestInfo, response: ResponseInfo) -> None:
        capture_response_headers(span, request, response)
        run_hook(hook, span, request, response)

    return capture_response_headers_hook


def make_capture_async_response_headers_hook(hook: AsyncResponseHook | None) -> AsyncResponseHook:
    async def capture_response_headers_hook(span: Span, request: RequestInfo, response: ResponseInfo) -> None:
        capture_response_headers(span, request, response)
        await run_async_hook(hook, span, request, response)

    return capture_response_headers_hook


def make_capture_request_headers_hook(hook: RequestHook | None) -> RequestHook:
    def capture_request_headers_hook(span: Span, request: RequestInfo) -> None:
        capture_request_headers(span, request)
        run_hook(hook, span, request)

    return capture_request_headers_hook


def make_capture_async_request_headers_hook(hook: AsyncRequestHook | None) -> AsyncRequestHook:
    async def capture_request_headers_hook(span: Span, request: RequestInfo) -> None:
        capture_request_headers(span, request)
        await run_async_hook(hook, span, request)

    return capture_request_headers_hook


async def run_async_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None:
    if hook:
        result = hook(*args, **kwargs)
        while inspect.isawaitable(result):
            result = await result


def run_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None:
    if hook:
        hook(*args, **kwargs)


def capture_response_headers(span: Span, request: RequestInfo, response: ResponseInfo) -> None:
    capture_headers(span, cast('httpx.Headers', response.headers), 'response')


def capture_request_headers(span: Span, request: RequestInfo) -> None:
    capture_headers(span, cast('httpx.Headers', request.headers), 'request')


def capture_headers(span: Span, headers: httpx.Headers, request_or_response: Literal['request', 'response']) -> None:
    span.set_attributes(
        {
            f'http.{request_or_response}.header.{header_name}': headers.get_list(header_name)
            for header_name in headers.keys()
        }
    )
