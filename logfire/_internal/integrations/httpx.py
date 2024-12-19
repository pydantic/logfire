from __future__ import annotations

import inspect
from contextlib import suppress
from email.message import Message
from typing import TYPE_CHECKING, Any, Callable, Literal, cast, overload

import httpx

from logfire.propagate import attach_context, get_context

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
from logfire._internal.main import set_user_attributes_on_raw_span
from logfire._internal.utils import handle_internal_errors

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
        capture_request_json_body: bool,
        capture_response_json_body: bool,
        **kwargs: Unpack[ClientKwargs],
    ) -> None: ...

    @overload
    def instrument_httpx(
        logfire_instance: Logfire,
        client: httpx.AsyncClient,
        capture_request_headers: bool,
        capture_response_headers: bool,
        capture_request_json_body: bool,
        capture_response_json_body: bool,
        **kwargs: Unpack[AsyncClientKwargs],
    ) -> None: ...

    @overload
    def instrument_httpx(
        logfire_instance: Logfire,
        client: None,
        capture_request_headers: bool,
        capture_response_headers: bool,
        capture_request_json_body: bool,
        capture_response_json_body: bool,
        **kwargs: Unpack[HTTPXInstrumentKwargs],
    ) -> None: ...


def instrument_httpx(
    logfire_instance: Logfire,
    client: httpx.Client | httpx.AsyncClient | None,
    capture_request_headers: bool,
    capture_response_headers: bool,
    capture_request_json_body: bool,
    capture_response_json_body: bool,
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
    del kwargs  # make sure only final_kwargs is used

    instrumentor = HTTPXClientInstrumentor()
    logfire_instance = logfire_instance.with_settings(custom_scope_suffix='httpx')

    if client is None:
        request_hook = cast('RequestHook | None', final_kwargs.get('request_hook'))
        response_hook = cast('ResponseHook | None', final_kwargs.get('response_hook'))
        async_request_hook = cast('AsyncRequestHook | None', final_kwargs.get('async_request_hook'))
        async_response_hook = cast('AsyncResponseHook | None', final_kwargs.get('async_response_hook'))
        final_kwargs['request_hook'] = make_request_hook(
            request_hook, capture_request_headers, capture_request_json_body
        )
        final_kwargs['response_hook'] = make_response_hook(
            response_hook, capture_response_headers, capture_response_json_body, logfire_instance
        )
        final_kwargs['async_request_hook'] = make_async_request_hook(
            async_request_hook, capture_request_headers, capture_request_json_body
        )
        final_kwargs['async_response_hook'] = make_async_response_hook(
            async_response_hook, capture_response_headers, capture_response_json_body, logfire_instance
        )

        instrumentor.instrument(**final_kwargs)
    else:
        if isinstance(client, httpx.AsyncClient):
            request_hook = cast('RequestHook | AsyncRequestHook | None', final_kwargs.get('request_hook'))
            response_hook = cast('ResponseHook | AsyncResponseHook | None', final_kwargs.get('response_hook'))

            request_hook = make_async_request_hook(request_hook, capture_request_headers, capture_request_json_body)
            response_hook = make_async_response_hook(
                response_hook, capture_response_headers, capture_response_json_body, logfire_instance
            )
        else:
            request_hook = cast('RequestHook | None', final_kwargs.get('request_hook'))
            response_hook = cast('ResponseHook | None', final_kwargs.get('response_hook'))

            request_hook = make_request_hook(request_hook, capture_request_headers, capture_request_json_body)
            response_hook = make_response_hook(
                response_hook, capture_response_headers, capture_response_json_body, logfire_instance
            )

        tracer_provider = final_kwargs['tracer_provider']
        instrumentor.instrument_client(client, tracer_provider, request_hook, response_hook)


def make_request_hook(
    hook: RequestHook | None, should_capture_headers: bool, should_capture_json: bool
) -> RequestHook | None:
    if not should_capture_headers and not should_capture_json and not hook:
        return None

    def new_hook(span: Span, request: RequestInfo) -> None:
        with handle_internal_errors():
            if should_capture_headers:
                capture_request_headers(span, request)
            if should_capture_json:
                capture_request_body(span, request)
            run_hook(hook, span, request)

    return new_hook


def make_async_request_hook(
    hook: AsyncRequestHook | RequestHook | None, should_capture_headers: bool, should_capture_json: bool
) -> AsyncRequestHook | None:
    if not should_capture_headers and not should_capture_json and not hook:
        return None

    async def new_hook(span: Span, request: RequestInfo) -> None:
        with handle_internal_errors():
            if should_capture_headers:
                capture_request_headers(span, request)
            if should_capture_json:
                capture_request_body(span, request)
            await run_async_hook(hook, span, request)

    return new_hook


def make_response_hook(
    hook: ResponseHook | None, should_capture_headers: bool, should_capture_json: bool, logfire_instance: Logfire
) -> ResponseHook | None:
    if not should_capture_headers and not should_capture_json and not hook:
        return None

    def new_hook(span: Span, request: RequestInfo, response: ResponseInfo) -> None:
        with handle_internal_errors():
            if should_capture_headers:
                capture_response_headers(span, response)
            if should_capture_json:
                capture_response_json(logfire_instance, response, False)
            run_hook(hook, span, request, response)

    return new_hook


def make_async_response_hook(
    hook: ResponseHook | AsyncResponseHook | None,
    should_capture_headers: bool,
    should_capture_json: bool,
    logfire_instance: Logfire,
) -> AsyncResponseHook | None:
    if not should_capture_headers and not should_capture_json and not hook:
        return None

    async def new_hook(span: Span, request: RequestInfo, response: ResponseInfo) -> None:
        with handle_internal_errors():
            if should_capture_headers:
                capture_response_headers(span, response)
            if should_capture_json:
                capture_response_json(logfire_instance, response, True)
            await run_async_hook(hook, span, request, response)

    return new_hook


def capture_response_json(logfire_instance: Logfire, response_info: ResponseInfo, is_async: bool) -> None:
    headers = cast('httpx.Headers', response_info.headers)
    if not headers.get('content-type', '').lower().startswith('application/json'):
        return

    frame = inspect.currentframe().f_back.f_back  # type: ignore
    while frame:
        response = frame.f_locals.get('response')
        frame = frame.f_back
        if isinstance(response, httpx.Response):  # pragma: no branch
            break
    else:  # pragma: no cover
        return

    ctx = get_context()
    attr_name = 'http.response.body.json'

    if is_async:  # these two branches should be kept almost identical
        original_aread = response.aread

        async def aread(*args: Any, **kwargs: Any):
            try:
                # Only log the body the first time it's read
                return response.content
            except httpx.ResponseNotRead:
                pass
            with attach_context(ctx), logfire_instance.span('Reading response body') as span:
                content = await original_aread(*args, **kwargs)
                span.set_attribute(attr_name, {})  # Set the JSON schema
                # Set the attribute to the raw text so that the backend can parse it
                span._span.set_attribute(attr_name, response.text)  # type: ignore
            return content

        response.aread = aread
    else:
        original_read = response.read

        def read(*args: Any, **kwargs: Any):
            try:
                # Only log the body the first time it's read
                return response.content
            except httpx.ResponseNotRead:
                pass
            with attach_context(ctx), logfire_instance.span('Reading response body') as span:
                content = original_read(*args, **kwargs)
                span.set_attribute(attr_name, {})  # Set the JSON schema
                # Set the attribute to the raw text so that the backend can parse it
                span._span.set_attribute(attr_name, response.text)  # type: ignore
            return content

        response.read = read


async def run_async_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None:
    if hook:
        result = hook(*args, **kwargs)
        while inspect.isawaitable(result):
            result = await result


def run_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None:
    if hook:
        hook(*args, **kwargs)


def capture_response_headers(span: Span, response: ResponseInfo) -> None:
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


def get_charset(content_type: str) -> str:
    m = Message()
    m['content-type'] = content_type
    return cast(str, m.get_param('charset', 'utf-8'))


def decode_body(body: bytes, content_type: str):
    charset = get_charset(content_type)
    with suppress(UnicodeDecodeError, LookupError):
        return body.decode(charset)
    if charset.lower() not in ('utf-8', 'utf8'):
        with suppress(UnicodeDecodeError):
            return body.decode('utf-8')
    return body.decode(charset, errors='replace')


def capture_request_body(span: Span, request: RequestInfo) -> None:
    content_type = cast('httpx.Headers', request.headers).get('content-type', '').lower()
    if not isinstance(request.stream, httpx.ByteStream):
        return
    if not content_type.startswith('application/json'):
        return

    body = decode_body(list(request.stream)[0], content_type)

    attr_name = 'http.request.body.json'
    set_user_attributes_on_raw_span(span, {attr_name: {}})  # type: ignore
    span.set_attribute(attr_name, body)
