from aiohttp.client_reqrep import ClientResponse
from aiohttp.tracing import TraceRequestEndParams, TraceRequestExceptionParams, TraceRequestStartParams
from logfire import Logfire as Logfire, LogfireSpan as LogfireSpan
from logfire._internal.utils import handle_internal_errors as handle_internal_errors
from logfire.integrations.aiohttp_client import AioHttpRequestHeaders as AioHttpRequestHeaders, AioHttpResponseHeaders as AioHttpResponseHeaders, RequestHook as RequestHook, ResponseHook as ResponseHook
from opentelemetry.trace import Span
from typing import Any, Callable, Literal, ParamSpec
from yarl import URL

P = ParamSpec('P')

def instrument_aiohttp_client(logfire_instance: Logfire, capture_response_body: bool, capture_headers: bool, request_hook: RequestHook | None, response_hook: ResponseHook | None, **kwargs: Any) -> None:
    """Instrument the `aiohttp` module so that spans are automatically created for each client request.

    See the `Logfire.instrument_aiohttp_client` method for details.
    """

class LogfireClientInfoMixin:
    headers: AioHttpRequestHeaders

class LogfireAioHttpRequestInfo(TraceRequestStartParams, LogfireClientInfoMixin):
    span: Span
    def capture_headers(self) -> None: ...

class LogfireAioHttpResponseInfo(LogfireClientInfoMixin):
    span: Span
    method: str
    url: URL
    headers: AioHttpRequestHeaders
    response: ClientResponse | None
    exception: BaseException | None
    logfire_instance: Logfire
    body_captured: bool
    def capture_headers(self) -> None: ...
    def capture_body_if_text(self, attr_name: str = 'http.response.body.text') -> None: ...
    def capture_text_as_json(self, span: LogfireSpan, *, text: str, attr_name: str) -> None: ...
    @classmethod
    def create_from_trace_params(cls, span: Span, params: TraceRequestEndParams | TraceRequestExceptionParams, logfire_instance: Logfire) -> LogfireAioHttpResponseInfo: ...

def make_request_hook(hook: RequestHook | None, capture_headers: bool) -> RequestHook | None: ...
def make_response_hook(hook: ResponseHook | None, logfire_instance: Logfire, capture_headers: bool, capture_response_body: bool) -> ResponseHook | None: ...
def capture_request(span: Span, request: TraceRequestStartParams, capture_headers: bool) -> LogfireAioHttpRequestInfo: ...
def capture_response(span: Span, response: TraceRequestEndParams | TraceRequestExceptionParams, logfire_instance: Logfire, capture_headers: bool, capture_response_body: bool) -> LogfireAioHttpResponseInfo: ...
def run_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None: ...
def capture_request_or_response_headers(span: Span, headers: AioHttpRequestHeaders | AioHttpResponseHeaders, request_or_response: Literal['request', 'response']) -> None: ...
