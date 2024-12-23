from __future__ import annotations

import inspect
from contextlib import suppress
from email.headerregistry import ContentTypeHeader
from email.policy import EmailPolicy
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Callable, Literal, Mapping, cast

import httpx
import opentelemetry.sdk.trace

from logfire._internal.stack_info import warn_at_user_stacklevel
from logfire.propagate import attach_context, get_context

try:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    from logfire.integrations.httpx import (
        AsyncRequestHook,
        AsyncResponseHook,
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
    from typing import ParamSpec, TypedDict, TypeVar

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


def instrument_httpx(
    logfire_instance: Logfire,
    client: httpx.Client | httpx.AsyncClient | None,
    capture_headers: bool,
    capture_request_json_body: bool,
    capture_response_json_body: bool,
    capture_request_form_data: bool,
    **kwargs: Any,
) -> None:
    """Instrument the `httpx` module so that spans are automatically created for each request.

    See the `Logfire.instrument_httpx` method for details.
    """
    capture_request_headers = kwargs.get('capture_request_headers')
    capture_response_headers = kwargs.get('capture_response_headers')

    if capture_request_headers is not None:
        warn_at_user_stacklevel(
            'The `capture_request_headers` parameter is deprecated. Use `capture_headers` instead.', DeprecationWarning
        )
    if capture_response_headers is not None:
        warn_at_user_stacklevel(
            'The `capture_response_headers` parameter is deprecated. Use `capture_headers` instead.', DeprecationWarning
        )

    should_capture_request_headers = capture_request_headers or capture_headers
    should_capture_response_headers = capture_response_headers or capture_headers

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
            request_hook, should_capture_request_headers, capture_request_json_body, capture_request_form_data
        )
        final_kwargs['response_hook'] = make_response_hook(
            response_hook, should_capture_response_headers, capture_response_json_body, logfire_instance
        )
        final_kwargs['async_request_hook'] = make_async_request_hook(
            async_request_hook, should_capture_request_headers, capture_request_json_body, capture_request_form_data
        )
        final_kwargs['async_response_hook'] = make_async_response_hook(
            async_response_hook, should_capture_response_headers, capture_response_json_body, logfire_instance
        )

        instrumentor.instrument(**final_kwargs)
    else:
        if isinstance(client, httpx.AsyncClient):
            request_hook = cast('RequestHook | AsyncRequestHook | None', final_kwargs.get('request_hook'))
            response_hook = cast('ResponseHook | AsyncResponseHook | None', final_kwargs.get('response_hook'))

            request_hook = make_async_request_hook(
                request_hook, should_capture_request_headers, capture_request_json_body, capture_request_form_data
            )
            response_hook = make_async_response_hook(
                response_hook, should_capture_response_headers, capture_response_json_body, logfire_instance
            )
        else:
            request_hook = cast('RequestHook | None', final_kwargs.get('request_hook'))
            response_hook = cast('ResponseHook | None', final_kwargs.get('response_hook'))

            request_hook = make_request_hook(
                request_hook, should_capture_request_headers, capture_request_json_body, capture_request_form_data
            )
            response_hook = make_response_hook(
                response_hook, should_capture_response_headers, capture_response_json_body, logfire_instance
            )

        tracer_provider = final_kwargs['tracer_provider']
        instrumentor.instrument_client(client, tracer_provider, request_hook, response_hook)  # type: ignore[reportArgumentType]


def make_request_hook(
    hook: RequestHook | None, should_capture_headers: bool, should_capture_json: bool, should_capture_form_data: bool
) -> RequestHook | None:
    if not should_capture_headers and not should_capture_json and not should_capture_form_data and not hook:
        return None

    def new_hook(span: Span, request: RequestInfo) -> None:
        with handle_internal_errors():
            capture_request(request, span, should_capture_headers, should_capture_json, should_capture_form_data)
            run_hook(hook, span, request)

    return new_hook


def make_async_request_hook(
    hook: AsyncRequestHook | RequestHook | None,
    should_capture_headers: bool,
    should_capture_json: bool,
    should_capture_form_data: bool,
) -> AsyncRequestHook | None:
    if not should_capture_headers and not should_capture_json and not should_capture_form_data and not hook:
        return None

    async def new_hook(span: Span, request: RequestInfo) -> None:
        with handle_internal_errors():
            capture_request(request, span, should_capture_headers, should_capture_json, should_capture_form_data)
            await run_async_hook(hook, span, request)

    return new_hook


def capture_request(
    request: RequestInfo,
    span: Span,
    should_capture_headers: bool,
    should_capture_json: bool,
    should_capture_form_data: bool,
) -> None:
    if should_capture_headers:
        capture_request_headers(span, request)
    if should_capture_json:
        capture_request_body(span, request)
    if should_capture_form_data:
        capture_request_form_data(span, request)


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
    if not is_json_type(response_info.headers.get('content-type', '')):
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
    capture_headers(span, response.headers, 'response')


def capture_request_headers(span: Span, request: RequestInfo) -> None:
    capture_headers(span, request.headers, 'request')


def capture_headers(span: Span, headers: httpx.Headers, request_or_response: Literal['request', 'response']) -> None:
    span.set_attributes(
        {
            f'http.{request_or_response}.header.{header_name}': headers.get_list(header_name)
            for header_name in headers.keys()
        }
    )


def decode_body(body: bytes, charset: str):
    with suppress(UnicodeDecodeError, LookupError):
        return body.decode(charset)
    if charset.lower() not in ('utf-8', 'utf8'):
        with suppress(UnicodeDecodeError):
            return body.decode('utf-8')
    return body.decode(charset, errors='replace')


def capture_request_body(span: Span, request: RequestInfo) -> None:
    if not isinstance(request.stream, httpx.ByteStream):
        return

    content_type_string = request.headers.get('content-type', '')
    if not is_json_type(content_type_string):
        return

    content_type_header = content_type_header_from_string(content_type_string)
    charset = content_type_header.params.get('charset', 'utf-8')
    body = decode_body(list(request.stream)[0], charset)

    attr_name = 'http.request.body.json'
    set_user_attributes_on_raw_span(span, {attr_name: {}})  # type: ignore
    span.set_attribute(attr_name, body)


CODES_FOR_METHODS_WITH_DATA_PARAM = [
    inspect.unwrap(method).__code__
    for method in [
        httpx.Client.request,
        httpx.Client.stream,
        httpx.AsyncClient.request,
        httpx.AsyncClient.stream,
    ]
]


def capture_request_form_data(span: Span, request: RequestInfo) -> None:
    content_type = request.headers.get('content-type', '')
    if content_type != 'application/x-www-form-urlencoded':
        return

    frame = inspect.currentframe().f_back.f_back.f_back  # type: ignore
    while frame:
        if frame.f_code in CODES_FOR_METHODS_WITH_DATA_PARAM:
            break
        frame = frame.f_back
    else:  # pragma: no cover
        return

    data = frame.f_locals.get('data')
    if not (data and isinstance(data, Mapping)):  # pragma: no cover
        return
    span = cast(opentelemetry.sdk.trace.Span, span)
    set_user_attributes_on_raw_span(span, {'http.request.body.form': data})


@lru_cache
def content_type_header_from_string(content_type: str) -> ContentTypeHeader:
    return EmailPolicy.header_factory('content-type', content_type)


def content_type_subtypes(subtype: str) -> set[str]:
    if subtype.startswith('x-'):
        subtype = subtype[2:]
    return set(subtype.split('+'))


@lru_cache
def is_json_type(content_type: str) -> bool:
    header = content_type_header_from_string(content_type)
    return header.maintype == 'application' and 'json' in content_type_subtypes(header.subtype)


TEXT_SUBTYPES = {
    'json',
    'jsonp',
    'json-p',
    'javascript',
    'jsonl',
    'json-l',
    'jsonlines',
    'json-lines',
    'ndjson',
    'nd-json',
    'json5',
    'json-5',
    'xml',
    'xhtml',
    'html',
    'csv',
    'tsv',
    'yaml',
    'yml',
    'toml',
}


@lru_cache
def is_text_type(content_type: str) -> bool:
    header = content_type_header_from_string(content_type)
    if header.maintype == 'text':
        return True
    if header.maintype != 'application':
        return False

    return bool(content_type_subtypes(header.subtype) & TEXT_SUBTYPES)
