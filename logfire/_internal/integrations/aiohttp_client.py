from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Literal, cast

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
from logfire._internal.config import GLOBAL_CONFIG
from logfire._internal.stack_info import warn_at_user_stacklevel
from logfire._internal.utils import handle_internal_errors
from logfire.integrations.aiohttp_client import AioHttpRequestHeaders, AioHttpResponseHeaders, RequestHook, ResponseHook

if TYPE_CHECKING:
    from typing import ParamSpec

    P = ParamSpec('P')


def instrument_aiohttp_client(
    logfire_instance: Logfire,
    capture_all: bool | None,
    capture_headers: bool,
    capture_request_body: bool,
    capture_response_body: bool,
    request_hook: RequestHook | None,
    response_hook: ResponseHook | None,
    **kwargs: Any,
) -> None:
    """Instrument the `aiohttp` module so that spans are automatically created for each client request.

    See the `Logfire.instrument_aiohttp_client` method for details.
    """
    logfire_instance = logfire_instance.with_settings(custom_scope_suffix='aiohttp_client')

    capture_all = cast(bool, GLOBAL_CONFIG.param_manager.load_param('aiohttp_client_capture_all', capture_all))

    if capture_all and (capture_headers or capture_request_body or capture_response_body):
        warn_at_user_stacklevel(
            'You should use either `capture_all` or the specific capture parameters, not both.', UserWarning
        )
    AioHttpClientInstrumentor().instrument(
        **{
            'tracer_provider': logfire_instance.config.get_tracer_provider(),
            'request_hook': make_request_hook(
                request_hook, capture_headers | capture_all, capture_request_body | capture_all
            ),
            'response_hook': make_response_hook(
                response_hook,
                capture_headers | capture_all,
                capture_response_body | capture_all,
                logfire_instance,
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
        capture_request_or_response_headers(self.span, self.response.headers if self.response else None, 'response')

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


def make_request_hook(hook: RequestHook | None, capture_headers: bool, capture_body: bool) -> RequestHook | None:
    if not (capture_headers or capture_body or hook):
        return None

    def new_hook(span: Span, request: TraceRequestStartParams) -> None:
        with handle_internal_errors:
            capture_request(span, request, capture_headers, capture_body)
            run_hook(hook, span, request)

    return new_hook


def make_response_hook(
    hook: ResponseHook | None,
    capture_headers: bool,
    capture_body: bool,
    logfire_instance: Logfire,
) -> ResponseHook | None:
    if not (capture_headers or capture_body or hook):
        return None

    def new_hook(span: Span, response: TraceRequestEndParams | TraceRequestExceptionParams) -> None:
        with handle_internal_errors:
            capture_response(
                span,
                response,
                logfire_instance,
                capture_headers,
                capture_body,
            )
            run_hook(hook, span, response)

    return new_hook


def capture_request(
    span: Span,
    request: TraceRequestStartParams,
    capture_headers: bool,
    _capture_body: bool,
) -> LogfireAioHttpRequestInfo:
    request_info = LogfireAioHttpRequestInfo(method=request.method, url=request.url, headers=request.headers, span=span)
    # TODO: Implement Request Body Capture, not implemented yet so capture request is not doing anything right now

    if capture_headers:
        request_info.capture_headers()

    return request_info


def capture_response(
    span: Span,
    response: TraceRequestEndParams | TraceRequestExceptionParams,
    logfire_instance: Logfire,
    capture_headers: bool,
    _capture_body: bool,
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
    headers: AioHttpRequestHeaders | AioHttpResponseHeaders | None,
    request_or_response: Literal['request', 'response'],
) -> None:
    if not headers:
        return
    span.set_attributes(
        {
            f'http.{request_or_response}.header.{header_name}': headers.getall(header_name)
            for header_name in headers.keys()
        }
    )
