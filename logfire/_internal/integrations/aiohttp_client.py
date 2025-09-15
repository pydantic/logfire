from __future__ import annotations

import functools
from email.headerregistry import ContentTypeHeader
from email.policy import EmailPolicy
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Callable, Literal, cast

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
from logfire._internal.config import GLOBAL_CONFIG
from logfire._internal.stack_info import warn_at_user_stacklevel
from logfire._internal.utils import handle_internal_errors
from logfire.integrations.aiohttp_client import AioHttpHeaders, RequestHook, ResponseHook

if TYPE_CHECKING:
    from typing import ParamSpec

    P = ParamSpec('P')

def run_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None:
    if hook:
        hook(*args, **kwargs)


def capture_request(
    span: Span,
    request: TraceRequestStartParams,
    should_capture_headers: bool,
    should_capture_body: bool,
) -> LogfireAiohttpRequestInfo:
    request_info = LogfireAiohttpRequestInfo(
        method=request.method,
        url=request.url,
        headers=request.headers,
        span=span
    )

    if should_capture_headers:
        request_info.capture_headers()

    return request_info


def capture_response(
    span: Span,
    response: TraceRequestEndParams | TraceRequestExceptionParams,
    logfire_instance: Logfire,
    capture_headers: bool,
    capture_body: bool,
) -> LogfireAiohttpResponseInfo:
    response_info = LogfireAiohttpResponseInfo.from_trace(span=span, params=response, logfire_instance=logfire_instance)

    if capture_headers:
        response_info.capture_headers()
    if capture_body:
        response_info.capture_body_if_text()
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


def make_request_hook(hook: RequestHook | None, capture_headers: bool, capture_body: bool) -> RequestHook | None:
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


class LogfireAiohttpClientInfoMixin:
    headers: AioHttpHeaders

    @property
    def content_type_header_object(self) -> ContentTypeHeader:
        return content_type_header_from_string(self.content_type_header_string)

    @property
    def content_type_header_string(self) -> str:
        return self.headers.get('content-type', '')

@attr.s(auto_attribs=True, frozen=True, slots=True)
class LogfireAiohttpRequestInfo(TraceRequestStartParams, LogfireAiohttpClientInfoMixin):
    span: Span

    def capture_headers(self):
        capture_request_or_response_headers(self.span, self.headers, 'request')



@attr.s(auto_attribs=True, frozen=True, slots=True)
class LogfireAiohttpResponseInfo(LogfireAiohttpClientInfoMixin):
    span: Span
    method: str
    url: URL
    headers: AioHttpHeaders
    response: ClientResponse | None
    exception: BaseException | None
    logfire_instance: Logfire

    def capture_headers(self):
        capture_request_or_response_headers(self.span, self.headers, 'response')


    def capture_body_if_text(self, attr_name: str = 'http.response.body.text') -> None:
        response = self.response
        if response is None:
            return

        if getattr(response, '__logfire_response_read_wrapped', False):
            return

        original_read = response.read

        @functools.wraps(original_read)
        async def read() -> bytes:
            with use_span(NonRecordingSpan(self.span.get_span_context())), self.logfire_instance.span('Reading response body') as span:
                body = await original_read()
                try:
                    encoding = response.get_encoding()
                    text = body.decode(encoding)
                except (UnicodeDecodeError, LookupError, RuntimeError):
                    setattr(response, '__logfire_body_captured', True)
                    return body
                self.capture_text_as_json(span, text=text, attr_name=attr_name)
                setattr(response, '__logfire_body_captured', True)
                return body

        response.read = read
        setattr(response, '__logfire_response_read_wrapped', True)

    def capture_text_as_json(self, span: LogfireSpan, *, text: str, attr_name: str) -> None:
        span.set_attribute(attr_name, {})
        span._span.set_attribute(attr_name, text)  # type: ignore[attr-defined]


    @classmethod
    def from_trace(
        cls,
        span: Span,
        params: TraceRequestEndParams | TraceRequestExceptionParams,
        logfire_instance: Logfire,
    ) -> LogfireAiohttpResponseInfo:
        """Build a LogfireAiohttpResponseInfo from either TraceRequestEndParams or TraceRequestExceptionParams.

        We use getattr so the factory works regardless of which concrete trace object is passed.
        """
        return cls(
            span=span,
            method=params.method,
            url=params.url,
            headers=params.headers,
            response=getattr(params, 'response', None),
            exception=getattr(params, 'exception', None),
            logfire_instance=logfire_instance,
        )


@lru_cache
def content_type_header_from_string(content_type: str) -> ContentTypeHeader:
    return EmailPolicy.header_factory('content-type', content_type)
