from __future__ import annotations
from typing import Any, Literal, Callable, cast

from aiohttp import ClientResponse

try:
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_aiohttp_client()` requires the `opentelemetry-instrumentation-aiohttp-client` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[aiohttp-client]'"
    )
from logfire import Logfire
from logfire.integrations.aiohttp_client import RequestHook, ResponseHook, AioHttpHeaders, LogfireAiohttpRequestInfo as PublicLogfireAiohttpRequestInfo, InternalRequestHook
from aiohttp.tracing import TraceRequestStartParams, TraceRequestEndParams
from email.headerregistry import ContentTypeHeader
from opentelemetry.trace import Span
from logfire._internal.utils import handle_internal_errors
from typing import ParamSpec
from logfire._internal.config import GLOBAL_CONFIG
from logfire._internal.stack_info import warn_at_user_stacklevel
from functools import lru_cache
from email.policy import EmailPolicy
import attr

P = ParamSpec('P')


def run_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None:
    if hook:
        hook(*args, **kwargs)


def capture_request(
    span: Span,
    request: TraceRequestStartParams,
    should_capture_headers: bool,
    should_capture_body: bool,
) -> PublicLogfireAiohttpRequestInfo:
    request_info = PublicLogfireAiohttpRequestInfo(
        method=request.method,
        url=request.url,
        headers=request.headers,
        span=span
    )

    if should_capture_headers:
        request_info.capture_headers()
    # if should_capture_body:
    #     request_info.capture_body()

    return request_info


def capture_response(
    span: Span,
    response: TraceRequestEndParams,
    capture_headers: bool,
    capture_body: bool,
) -> LogfireAiohttpResponseInfo:
    # Get response headers from the response object
    response_info = LogfireAiohttpResponseInfo(
        span=span,
        method=response.method,
        url=response.url,
        headers=response.headers,
        response=response.response
    )

    if capture_headers:
        response_info.capture_headers()
    if capture_body:
        response_info.capture_body()

    return response_info


def capture_request_or_response_headers(
    span: Span, headers: AioHttpHeaders, request_or_response: Literal['request', 'response']
) -> None:
    span.set_attributes(
        {
            f'http.{request_or_response}.header.{header_name}': headers.getall(header_name)
            for header_name in headers.keys()
        }
    )

def capture_response_body(span: Span, response: ClientResponse) -> None:
    span.set_attribute('http.response.body', response.text())


def make_request_hook(hook: RequestHook | None, capture_headers: bool, capture_body: bool) -> InternalRequestHook | None:
    if not (capture_headers or capture_body or hook):
        return None

    def new_hook(span: Span, request: TraceRequestStartParams) -> None:
        with handle_internal_errors:
            request_info = capture_request(span, request, capture_headers, capture_body)
            run_hook(hook, span, request_info)

    return new_hook


def make_response_hook(
    hook: ResponseHook | None,
    capture_headers: bool,
    capture_body: bool,
) -> ResponseHook | None:
    if not (capture_headers or capture_body or hook):
        return None

    def new_hook(span: Span, response: TraceRequestEndParams) -> None:
        with handle_internal_errors:
            response_info = capture_response(
                span,
                response,
                capture_headers,
                capture_body,
            )
            run_hook(hook, span, response_info)

    return new_hook


def instrument_aiohttp_client(
    logfire_instance: Logfire,
    capture_all: bool,
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
            'request_hook': make_request_hook(request_hook, capture_headers | capture_all, capture_request_body | capture_all),
            'response_hook': make_response_hook(response_hook, capture_headers | capture_all, capture_response_body | capture_all),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            **kwargs,
        },
    )


class LogfireAiohttpClientInfoMixin:
    headers: AioHttpHeaders

    @property
    def content_type_header_object(self) -> ContentTypeHeader:
        return content_type_header_from_string(self.content_type_header_string)

    @property
    def content_type_header_string(self) -> str:
        return self.headers.get('content-type', '')


class LogfireAiohttpRequestInfo(TraceRequestStartParams, LogfireAiohttpClientInfoMixin):
    span: Span

    def capture_headers(self):
        capture_request_or_response_headers(self.span, self.headers, 'request')

# TODO: Add TraceRequestExceptionParams support
@attr.s(auto_attribs=True, frozen=True, slots=True)
class LogfireAiohttpResponseInfo(LogfireAiohttpClientInfoMixin, TraceRequestEndParams):
    span: Span

    def capture_headers(self):
        capture_request_or_response_headers(self.span, self.headers, 'response')

    def capture_body(self):
        capture_response_body(self.span, self.response)

@lru_cache
def content_type_header_from_string(content_type: str) -> ContentTypeHeader:
    return EmailPolicy.header_factory('content-type', content_type)
