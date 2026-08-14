"""Public types for the Litestar integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from opentelemetry.metrics import Meter, MeterProvider
from opentelemetry.trace import Span, Tracer, TracerProvider

if TYPE_CHECKING:
    from litestar.types import Scopes

ServerRequestHook = Callable[[Span, dict[str, Any]], None]
ClientRequestHook = Callable[[Span, dict[str, Any], dict[str, Any]], None]
ClientResponseHook = Callable[[Span, dict[str, Any], dict[str, Any]], None]
AfterExceptionHook = Callable[[BaseException, dict[str, Any]], Awaitable[None] | None]
ScopeSpanDetailsExtractor = Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]


class LitestarInstrumentKwargs(TypedDict, total=False):
    """Additional options accepted by Litestar's OpenTelemetry configuration."""

    after_exception_hook_handler: AfterExceptionHook | None
    scope_span_details_extractor: ScopeSpanDetailsExtractor
    server_request_hook_handler: ServerRequestHook | None
    client_request_hook_handler: ClientRequestHook | None
    client_response_hook_handler: ClientResponseHook | None
    meter_provider: MeterProvider | None
    tracer_provider: TracerProvider | None
    tracer: Tracer | None
    meter: Meter | None
    exclude: str | list[str] | None
    exclude_opt_key: str | None
    exclude_urls_env_key: str
    exclude_spans: list[Literal['receive', 'send']] | None
    scopes: Scopes | None
    http_capture_headers_server_request: list[str] | None
    http_capture_headers_server_response: list[str] | None
    http_capture_headers_sanitize_fields: list[str] | None
    middleware_class: type[Any]
