from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Callable, Literal, cast, overload

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

    class AsyncClientKwargs(TypedDict, total=False):
        request_hook: RequestHook | AsyncRequestHook
        response_hook: ResponseHook | AsyncResponseHook
        skip_dep_check: bool

    class ClientKwargs(TypedDict, total=False):
        request_hook: RequestHook
        response_hook: ResponseHook
        skip_dep_check: bool

    class HTTPXInstrumentKwargs(TypedDict, total=False):
        request_hook: RequestHook
        response_hook: ResponseHook
        async_request_hook: AsyncRequestHook
        async_response_hook: AsyncResponseHook
        skip_dep_check: bool

    AnyRequestHook = TypeVar('AnyRequestHook', RequestHook, AsyncRequestHook)
    AnyResponseHook = TypeVar('AnyResponseHook', ResponseHook, AsyncResponseHook)
    Hook = TypeVar('Hook', RequestHook, ResponseHook)
    AsyncHook = TypeVar('AsyncHook', AsyncRequestHook, AsyncResponseHook)

    P = ParamSpec('P')

    @overload
    def instrument_httpx(
        logfire_instance: Logfire,
        client: httpx.Client,
        capture_request_headers: bool,
        capture_response_headers: bool,
        **kwargs: Unpack[ClientKwargs],
    ) -> None: ...

    @overload
    def instrument_httpx(
        logfire_instance: Logfire,
        client: httpx.AsyncClient,
        capture_request_headers: bool,
        capture_response_headers: bool,
        **kwargs: Unpack[AsyncClientKwargs],
    ) -> None: ...

    @overload
    def instrument_httpx(
        logfire_instance: Logfire,
        client: None,
        capture_request_headers: bool,
        capture_response_headers: bool,
        **kwargs: Unpack[HTTPXInstrumentKwargs],
    ) -> None: ...


def instrument_httpx(
    logfire_instance: Logfire,
    client: httpx.Client | httpx.AsyncClient | None,
    capture_request_headers: bool,
    capture_response_headers: bool,
    **kwargs: Any,
) -> None:
    """Instrument the `httpx` module so that spans are automatically created for each request.

    See the `Logfire.instrument_httpx` method for details.
    """
    final_kwargs: dict[str, Any] = {
        'tracer_provider': logfire_instance.config.get_tracer_provider(),
        'meter_provider': logfire_instance.config.get_meter_provider(),
        **kwargs,
    }

    instrumentor = HTTPXClientInstrumentor()

    if client is None:
        request_hook = cast('RequestHook | None', final_kwargs.get('request_hook'))
        response_hook = cast('ResponseHook | None', final_kwargs.get('response_hook'))
        async_request_hook = cast('AsyncRequestHook | None', final_kwargs.get('async_request_hook'))
        async_response_hook = cast('AsyncResponseHook | None', final_kwargs.get('async_response_hook'))

        if capture_request_headers:  # pragma: no cover
            final_kwargs['request_hook'] = make_capture_request_headers_hook(request_hook)
            final_kwargs['async_request_hook'] = make_capture_async_request_headers_hook(async_request_hook)

        if capture_response_headers:  # pragma: no cover
            final_kwargs['response_hook'] = make_capture_response_headers_hook(response_hook)
            final_kwargs['async_response_hook'] = make_capture_async_response_headers_hook(async_response_hook)

        del kwargs  # make sure only final_kwargs is used
        instrumentor.instrument(**final_kwargs)
    else:
        request_hook = cast('RequestHook | AsyncRequestHook | None', final_kwargs.get('request_hook'))
        response_hook = cast('ResponseHook | AsyncResponseHook | None', final_kwargs.get('response_hook'))

        if capture_request_headers:
            if isinstance(client, httpx.AsyncClient):
                request_hook = cast('AsyncRequestHook | None', request_hook)
                request_hook = make_capture_async_request_headers_hook(request_hook)
            else:
                request_hook = cast('RequestHook | None', request_hook)
                request_hook = make_capture_request_headers_hook(request_hook)

        if capture_response_headers:
            if isinstance(client, httpx.AsyncClient):
                response_hook = cast('AsyncResponseHook | None', response_hook)
                response_hook = make_capture_async_response_headers_hook(response_hook)
            else:
                response_hook = cast('ResponseHook | None', response_hook)
                response_hook = make_capture_response_headers_hook(response_hook)

        tracer_provider = final_kwargs['tracer_provider']
        instrumentor.instrument_client(client, tracer_provider, request_hook, response_hook)


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
