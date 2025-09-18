from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Callable, Literal

import attr
from aiohttp.client_reqrep import ClientResponse
from aiohttp.tracing import TraceRequestEndParams, TraceRequestExceptionParams, TraceRequestStartParams
from opentelemetry.trace import NonRecordingSpan, Span, use_span
from yarl import URL

try:
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_aiohttp_client()` requires the `opentelemetry-instrumentation-aiohttp-client` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[aiohttp-client]'"
    )

from logfire import Logfire, LogfireSpan
from logfire._internal.utils import handle_internal_errors
from logfire.integrations.aiohttp_client import AioHttpRequestHeaders, AioHttpResponseHeaders, RequestHook, ResponseHook

if TYPE_CHECKING:
    from typing import ParamSpec

    P = ParamSpec('P')


def instrument_aiohttp_client(
    logfire_instance: Logfire,
    capture_response_body: bool,
    capture_headers: bool,
    request_hook: RequestHook | None,
    response_hook: ResponseHook | None,
    **kwargs: Any,
) -> None:
    """Instrument the `aiohttp` module so that spans are automatically created for each client request.

    See the `Logfire.instrument_aiohttp_client` method for details.
    """
    logfire_instance = logfire_instance.with_settings(custom_scope_suffix='aiohttp_client')

    AioHttpClientInstrumentor().instrument(
        **{
            'tracer_provider': logfire_instance.config.get_tracer_provider(),
            'request_hook': make_request_hook(request_hook, capture_headers),
            'response_hook': make_response_hook(
                response_hook,
                logfire_instance,
                capture_headers,
                capture_response_body,
            ),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            **kwargs,
        },
    )


class LogfireClientInfoMixin:
    headers: AioHttpRequestHeaders


@attr.s(auto_attribs=True, frozen=True, slots=True)
class LogfireAioHttpRequestInfo(TraceRequestStartParams, LogfireClientInfoMixin):
    span: Span

    def capture_headers(self):
        capture_request_or_response_headers(self.span, self.headers, 'request')


@attr.s(auto_attribs=True, slots=True)
class LogfireAioHttpResponseInfo(LogfireClientInfoMixin):
    span: Span
    method: str
    url: URL
    headers: AioHttpRequestHeaders
    response: ClientResponse | None
    exception: BaseException | None
    logfire_instance: Logfire
    body_captured: bool = False

    def capture_headers(self):
        if self.response:
            capture_request_or_response_headers(self.span, self.response.headers, 'response')

    def capture_body_if_text(self, attr_name: str = 'http.response.body.text') -> None:
        response = self.response
        if response is None:
            return

        original_read = response.read

        @functools.wraps(original_read)
        async def read() -> bytes:
            if self.body_captured:
                return await original_read()

            with (
                use_span(NonRecordingSpan(self.span.get_span_context())),
                self.logfire_instance.span('Reading response body') as span,
            ):
                body = await original_read()
                try:
                    encoding = response.get_encoding()
                    text = body.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    self.body_captured = True
                    return body
                self.capture_text_as_json(span, text=text, attr_name=attr_name)
                self.body_captured = True
                return body

        response.read = read

    def capture_text_as_json(self, span: LogfireSpan, *, text: str, attr_name: str) -> None:
        span.set_attribute(attr_name, {})
        span._span.set_attribute(attr_name, text)  # type: ignore

    @classmethod
    def create_from_trace_params(
        cls,
        span: Span,
        params: TraceRequestEndParams | TraceRequestExceptionParams,
        logfire_instance: Logfire,
    ) -> LogfireAioHttpResponseInfo:
        return cls(
            span=span,
            method=params.method,
            url=params.url,
            headers=params.headers,
            response=getattr(params, 'response', None),
            exception=getattr(params, 'exception', None),
            logfire_instance=logfire_instance,
        )


def make_request_hook(hook: RequestHook | None, capture_headers: bool) -> RequestHook | None:
    if not (capture_headers or hook):
        return None

    def new_hook(span: Span, request: TraceRequestStartParams) -> None:
        with handle_internal_errors:
            capture_request(span, request, capture_headers)
            run_hook(hook, span, request)

    return new_hook


def make_response_hook(
    hook: ResponseHook | None,
    logfire_instance: Logfire,
    capture_headers: bool,
    capture_response_body: bool,
) -> ResponseHook | None:
    if not (capture_headers or capture_response_body or hook):
        return None

    def new_hook(span: Span, response: TraceRequestEndParams | TraceRequestExceptionParams) -> None:
        with handle_internal_errors:
            capture_response(
                span,
                response,
                logfire_instance,
                capture_headers,
                capture_response_body,
            )
            run_hook(hook, span, response)

    return new_hook


def capture_request(
    span: Span,
    request: TraceRequestStartParams,
    capture_headers: bool,
) -> LogfireAioHttpRequestInfo:
    request_info = LogfireAioHttpRequestInfo(method=request.method, url=request.url, headers=request.headers, span=span)

    if capture_headers:
        request_info.capture_headers()

    return request_info


def capture_response(
    span: Span,
    response: TraceRequestEndParams | TraceRequestExceptionParams,
    logfire_instance: Logfire,
    capture_headers: bool,
    capture_response_body: bool,
) -> LogfireAioHttpResponseInfo:
    response_info = LogfireAioHttpResponseInfo.create_from_trace_params(
        span=span, params=response, logfire_instance=logfire_instance
    )

    if capture_headers:
        response_info.capture_headers()

    if capture_response_body:
        response_info.capture_body_if_text()

    return response_info


def run_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None:
    if hook:
        hook(*args, **kwargs)


def capture_request_or_response_headers(
    span: Span,
    headers: AioHttpRequestHeaders | AioHttpResponseHeaders,
    request_or_response: Literal['request', 'response'],
) -> None:
    span.set_attributes(
        {
            f'http.{request_or_response}.header.{header_name}': headers.getall(header_name)
            for header_name in headers.keys()
        }
    )
