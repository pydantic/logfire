import httpx
from _typeshed import Incomplete
from collections.abc import Generator
from email.headerregistry import ContentTypeHeader
from functools import cached_property
from logfire import Logfire as Logfire, LogfireSpan as LogfireSpan
from logfire._internal.main import set_user_attributes_on_raw_span as set_user_attributes_on_raw_span
from logfire._internal.stack_info import warn_at_user_stacklevel as warn_at_user_stacklevel
from logfire._internal.utils import handle_internal_errors as handle_internal_errors
from logfire.integrations.httpx import AsyncRequestHook as AsyncRequestHook, AsyncResponseHook as AsyncResponseHook, RequestHook as RequestHook, RequestInfo as RequestInfo, ResponseHook as ResponseHook, ResponseInfo as ResponseInfo
from opentelemetry.trace import Span
from typing import Any, Awaitable, Callable, Literal, Mapping, ParamSpec

P = ParamSpec('P')

def instrument_httpx(logfire_instance: Logfire, client: httpx.Client | httpx.AsyncClient | None, capture_headers: bool, capture_request_body: bool, capture_response_body: bool, request_hook: RequestHook | AsyncRequestHook | None, response_hook: ResponseHook | AsyncResponseHook | None, async_request_hook: AsyncRequestHook | None, async_response_hook: AsyncResponseHook | None, **kwargs: Any) -> None:
    """Instrument the `httpx` module so that spans are automatically created for each request.

    See the `Logfire.instrument_httpx` method for details.
    """

class LogfireHttpxInfoMixin:
    headers: httpx.Headers
    @property
    def content_type_header_object(self) -> ContentTypeHeader: ...
    @property
    def content_type_header_string(self) -> str: ...

class LogfireHttpxRequestInfo(RequestInfo, LogfireHttpxInfoMixin):
    span: Span
    def capture_headers(self) -> None: ...
    def capture_body(self) -> None: ...
    def capture_body_if_text(self, attr_name: str = 'http.request.body.text'): ...
    def capture_body_if_form(self, attr_name: str = 'http.request.body.form') -> bool: ...
    def capture_text_as_json(self, attr_name: str, text: str): ...
    @property
    def body_is_streaming(self): ...
    @property
    def content_type_charset(self): ...
    @property
    def content(self) -> bytes: ...
    @cached_property
    def form_data(self) -> Mapping[str, Any] | None: ...
    def set_complex_span_attributes(self, attributes: dict[str, Any]): ...

class LogfireHttpxResponseInfo(ResponseInfo, LogfireHttpxInfoMixin):
    span: Span
    logfire_instance: Logfire
    is_async: bool
    def capture_headers(self) -> None: ...
    def capture_body_if_text(self, attr_name: str = 'http.response.body.text'): ...
    @cached_property
    def response(self) -> httpx.Response: ...
    def on_response_read(self, hook: Callable[[LogfireSpan], None]): ...
    def wrap_response_read(self, hook: Callable[[Callable[[], bytes]], bytes]): ...
    def wrap_response_aread(self, hook: Callable[[Callable[[], Awaitable[bytes]]], Awaitable[bytes]]): ...
    def attach_original_span_context(self) -> Generator[None]: ...
    def capture_text_as_json(self, span: LogfireSpan, *, text: str, attr_name: str): ...

def make_request_hook(hook: RequestHook | None, capture_headers: bool, capture_body: bool) -> RequestHook | None: ...
def make_async_request_hook(hook: AsyncRequestHook | RequestHook | None, should_capture_headers: bool, should_capture_body: bool) -> AsyncRequestHook | None: ...
def make_response_hook(hook: ResponseHook | None, capture_headers: bool, capture_body: bool, logfire_instance: Logfire) -> ResponseHook | None: ...
def make_async_response_hook(hook: ResponseHook | AsyncResponseHook | None, should_capture_headers: bool, should_capture_body: bool, logfire_instance: Logfire) -> AsyncResponseHook | None: ...
def capture_request(span: Span, request: RequestInfo, should_capture_headers: bool, should_capture_body: bool) -> LogfireHttpxRequestInfo: ...
def capture_response(span: Span, request: RequestInfo, response: ResponseInfo, logfire_instance: Logfire, capture_headers: bool, capture_body: bool, *, is_async: bool) -> tuple[LogfireHttpxRequestInfo, LogfireHttpxResponseInfo]: ...
async def run_async_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None: ...
def run_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None: ...
def capture_request_or_response_headers(span: Span, headers: httpx.Headers, request_or_response: Literal['request', 'response']) -> None: ...

CODES_FOR_METHODS_WITH_DATA_PARAM: Incomplete

def content_type_header_from_string(content_type: str) -> ContentTypeHeader: ...
def content_type_subtypes(subtype: str) -> set[str]: ...
def is_json_type(content_type: str) -> bool: ...
