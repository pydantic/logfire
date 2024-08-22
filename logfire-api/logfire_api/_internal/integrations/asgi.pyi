from dataclasses import dataclass
from logfire import Logfire as Logfire
from logfire._internal.utils import is_asgi_send_receive_span_name as is_asgi_send_receive_span_name
from opentelemetry.context import Context
from opentelemetry.trace import Span, Tracer, TracerProvider
from typing import Any

def tweak_asgi_spans_tracer_provider(logfire_instance: Logfire, record_send_receive: bool) -> TracerProvider:
    """If record_send_receive is False, return a TracerProvider that skips spans for ASGI send and receive events."""

@dataclass
class TweakAsgiTracerProvider(TracerProvider):
    tracer_provider: TracerProvider
    def get_tracer(self, *args: Any, **kwargs: Any) -> Tracer: ...

@dataclass
class TweakAsgiSpansTracer(Tracer):
    tracer: Tracer
    def start_span(self, name: str, context: Context | None = None, *args: Any, **kwargs: Any) -> Span: ...
    start_as_current_span = ...
