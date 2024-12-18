import httpx
from logfire import Logfire as Logfire
from opentelemetry.instrumentation.httpx import AsyncRequestHook, AsyncResponseHook, RequestHook, RequestInfo, ResponseHook, ResponseInfo
from opentelemetry.trace import Span
from typing import Any, Callable, Literal, ParamSpec, TypeVar, TypedDict, Unpack, overload

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
def instrument_httpx(logfire_instance: Logfire, client: httpx.Client, capture_request_headers: bool, capture_response_headers: bool, **kwargs: Unpack[ClientKwargs]) -> None: ...
@overload
def instrument_httpx(logfire_instance: Logfire, client: httpx.AsyncClient, capture_request_headers: bool, capture_response_headers: bool, **kwargs: Unpack[AsyncClientKwargs]) -> None: ...
@overload
def instrument_httpx(logfire_instance: Logfire, client: None, capture_request_headers: bool, capture_response_headers: bool, **kwargs: Unpack[HTTPXInstrumentKwargs]) -> None: ...
def make_capture_response_headers_hook(hook: ResponseHook | None) -> ResponseHook: ...
def make_capture_async_response_headers_hook(hook: AsyncResponseHook | None) -> AsyncResponseHook: ...
def make_capture_request_headers_hook(hook: RequestHook | None) -> RequestHook: ...
def make_capture_async_request_headers_hook(hook: AsyncRequestHook | None) -> AsyncRequestHook: ...
async def run_async_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None: ...
def run_hook(hook: Callable[P, Any] | None, *args: P.args, **kwargs: P.kwargs) -> None: ...
def capture_response_headers(span: Span, request: RequestInfo, response: ResponseInfo) -> None: ...
def capture_request_headers(span: Span, request: RequestInfo) -> None: ...
def capture_headers(span: Span, headers: httpx.Headers, request_or_response: Literal['request', 'response']) -> None: ...
