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
        httpx.SyncByteStream | httpx.AsyncByteStream | httpx2.SyncByteStream | httpx2.AsyncByteStream
    )
else:
    _HTTPXURL = _HTTPXHeaders = _HTTPXStream = Any


class RequestInfo(NamedTuple):
    """Information about an HTTP request.

    This is the second parameter passed to the `RequestHook` function.
    """

    method: bytes
    url: _HTTPXURL
    headers: _HTTPXHeaders
    stream: _HTTPXStream | None
    extensions: dict[str, Any] | None


class ResponseInfo(NamedTuple):
    """Information about an HTTP response.

    This is the second parameter passed to the `ResponseHook` function.
    """

    status_code: int
    headers: _HTTPXHeaders
    stream: _HTTPXStream | None
    extensions: dict[str, Any] | None


RequestHook = Callable[[Span, RequestInfo], None]
ResponseHook = Callable[[Span, RequestInfo, ResponseInfo], None]
AsyncRequestHook = Callable[[Span, RequestInfo], Awaitable[None]]
AsyncResponseHook = Callable[[Span, RequestInfo, ResponseInfo], Awaitable[None]]
