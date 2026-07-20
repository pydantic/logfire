from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, NamedTuple, TypeAlias

from opentelemetry.trace import Span

if TYPE_CHECKING:
    import httpx
    import httpx2

    _HTTPXURL: TypeAlias = httpx.URL | httpx2.URL
    _HTTPXHeaders: TypeAlias = httpx.Headers | httpx2.Headers
    _HTTPXStream: TypeAlias = (
        httpx.SyncByteStream | httpx.AsyncByteStream | httpx2.SyncByteStream | httpx2.AsyncByteStream | None
    )
else:
    _HTTPXURL = _HTTPXHeaders = _HTTPXStream = Any

# TODO(Marcelo): When https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3098/ gets merged,
# and the next version of `opentelemetry-instrumentation-httpx` is released, we can just do a reimport:
# from opentelemetry.instrumentation.httpx import RequestInfo as RequestInfo
# from opentelemetry.instrumentation.httpx import ResponseInfo as ResponseInfo
# from opentelemetry.instrumentation.httpx import RequestHook as RequestHook
# from opentelemetry.instrumentation.httpx import ResponseHook as ResponseHook


class RequestInfo(NamedTuple):
    """Information about an HTTP request.

    This is the second parameter passed to the `RequestHook` function.
    """

    method: bytes
    url: _HTTPXURL
    headers: _HTTPXHeaders
    stream: _HTTPXStream
    extensions: dict[str, Any] | None


class ResponseInfo(NamedTuple):
    """Information about an HTTP response.

    This is the second parameter passed to the `ResponseHook` function.
    """

    status_code: int
    headers: _HTTPXHeaders
    stream: _HTTPXStream
    extensions: dict[str, Any] | None


RequestHook = Callable[[Span, RequestInfo], None]
ResponseHook = Callable[[Span, RequestInfo, ResponseInfo], None]
AsyncRequestHook = Callable[[Span, RequestInfo], Awaitable[None]]
AsyncResponseHook = Callable[[Span, RequestInfo, ResponseInfo], Awaitable[None]]
