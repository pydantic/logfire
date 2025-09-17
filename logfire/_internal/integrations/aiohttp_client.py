from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Literal

import attr
from aiohttp.client_reqrep import ClientResponse
from aiohttp.tracing import TraceRequestEndParams, TraceRequestExceptionParams, TraceRequestStartParams
from opentelemetry.trace import Span
from yarl import URL

try:
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_aiohttp_client()` requires the `opentelemetry-instrumentation-aiohttp-client` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[aiohttp-client]'"
    )

from logfire import Logfire
from logfire._internal.utils import handle_internal_errors
from logfire.integrations.aiohttp_client import AioHttpRequestHeaders, AioHttpResponseHeaders, RequestHook, ResponseHook

if TYPE_CHECKING:
    from typing import ParamSpec

    P = ParamSpec('P')


def instrument_aiohttp_client(
    logfire_instance: Logfire,
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


@attr.s(auto_attribs=True, frozen=True, slots=True)
class LogfireAioHttpResponseInfo(LogfireClientInfoMixin):
    span: Span
    method: str
    url: URL
    headers: AioHttpRequestHeaders
    response: ClientResponse | None
    exception: BaseException | None
    logfire_instance: Logfire

    def capture_headers(self):
        if self.response:
            capture_request_or_response_headers(self.span, self.response.headers, 'response')

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
) -> ResponseHook | None:
    if not (capture_headers or hook):
        return None

    def new_hook(span: Span, response: TraceRequestEndParams | TraceRequestExceptionParams) -> None:
        with handle_internal_errors:
            capture_response(
                span,
                response,
                logfire_instance,
                capture_headers,
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
) -> LogfireAioHttpResponseInfo:
    response_info = LogfireAioHttpResponseInfo.create_from_trace_params(
        span=span, params=response, logfire_instance=logfire_instance
    )

    if capture_headers:
        response_info.capture_headers()

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
