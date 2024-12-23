import httpx
from _typeshed import Incomplete
from email.headerregistry import ContentTypeHeader
from logfire import Logfire as Logfire
from logfire._internal.main import set_user_attributes_on_raw_span as set_user_attributes_on_raw_span
from logfire._internal.stack_info import warn_at_user_stacklevel as warn_at_user_stacklevel
from logfire._internal.utils import handle_internal_errors as handle_internal_errors
from logfire.integrations.httpx import AsyncRequestHook as AsyncRequestHook, AsyncResponseHook as AsyncResponseHook, RequestHook as RequestHook, RequestInfo as RequestInfo, ResponseHook as ResponseHook, ResponseInfo as ResponseInfo
from logfire.propagate import attach_context as attach_context, get_context as get_context
from opentelemetry.trace import Span
from typing import Any, Callable, Literal, ParamSpec, TypeVar, TypedDict

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

def instrument_httpx(logfire_instance: Logfire, client: httpx.Client | httpx.AsyncClient | None, capture_headers: bool, capture_request_json_body: bool, capture_response_json_body: bool, capture_request_form_data: bool, **kwargs: Any) -> None:
    """Instrument the `httpx` module so that spans are automatically created for each request.

    See the `Logfire.instrument_httpx` method for details.
    """
def make_request_hook(hook: RequestHook | None, should_capture_headers: bool, should_capture_json: bool, should_capture_form_data: bool) -> RequestHook | None: ...
def make_async_request_hook(hook: AsyncRequestHook | RequestHook | None, should_capture_headers: bool, should_capture_json: bool, should_capture_form_data: bool) -> AsyncRequestHook | None: ...
def capture_request(request: RequestInfo, span: Span, should_capture_headers: bool, should_capture_json: bool, should_capture_form_data: bool) -> None: ...
def make_response_hook(hook: ResponseHook | None, should_capture_headers: bool, should_capture_json: bool, logfire_instance: Logfire) -> ResponseHook | None: ...
def make_async_response_hook(hook: ResponseHook | AsyncResponseHook | None, should_capture_headers: bool, should_capture_json: bool, logfire_instance: Logfire) -> AsyncResponseHook | None: ...
def capture_response_json(logfire_instance: Logfire, response_info: ResponseInfo, is_async: bool) -> None: ...
async def run_async_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None: ...
def run_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None: ...
def capture_response_headers(span: Span, response: ResponseInfo) -> None: ...
def capture_request_headers(span: Span, request: RequestInfo) -> None: ...
def capture_headers(span: Span, headers: httpx.Headers, request_or_response: Literal['request', 'response']) -> None: ...
def decode_body(body: bytes, charset: str): ...
def capture_request_body(span: Span, request: RequestInfo) -> None: ...

CODES_FOR_METHODS_WITH_DATA_PARAM: Incomplete

def capture_request_form_data(span: Span, request: RequestInfo) -> None: ...
def content_type_header_from_string(content_type: str) -> ContentTypeHeader: ...
def content_type_subtypes(subtype: str) -> set[str]: ...
def is_json_type(content_type: str) -> bool: ...

TEXT_SUBTYPES: Incomplete

def is_text_type(content_type: str) -> bool: ...
