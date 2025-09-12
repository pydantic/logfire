from __future__ import annotations
from typing import Callable
from aiohttp.tracing import TraceRequestStartParams, TraceRequestEndParams, TraceRequestExceptionParams
from opentelemetry.trace import Span
from multidict import CIMultiDict
from yarl import URL
from email.headerregistry import ContentTypeHeader
from functools import lru_cache
from email.policy import EmailPolicy


AioHttpHeaders = CIMultiDict[str]


class LogfireAiohttpClientInfoMixin:
    headers: AioHttpHeaders

    @property
    def content_type_header_object(self) -> ContentTypeHeader:
        return content_type_header_from_string(self.content_type_header_string)

    @property
    def content_type_header_string(self) -> str:
        return self.headers.get('content-type', '')


class LogfireAiohttpRequestInfo(LogfireAiohttpClientInfoMixin):
    def __init__(self, method: str, url: URL, headers: AioHttpHeaders, span: Span):
        self.method = method
        self.url = url
        self.headers = headers
        self.span = span

    def capture_headers(self):
        """Capture request headers and add them to the span."""
        # Import here to avoid circular import
        from logfire._internal.integrations.aiohttp_client import capture_request_or_response_headers
        capture_request_or_response_headers(self.span, self.headers, 'request')


@lru_cache
def content_type_header_from_string(content_type: str) -> ContentTypeHeader:
    return EmailPolicy.header_factory('content-type', content_type)


RequestHook = Callable[[Span, LogfireAiohttpRequestInfo], None]
# Internal type used by OpenTelemetry
InternalRequestHook = Callable[[Span, TraceRequestStartParams], None]
ResponseHook = Callable[[Span, TraceRequestStartParams, TraceRequestEndParams | TraceRequestExceptionParams], None]
