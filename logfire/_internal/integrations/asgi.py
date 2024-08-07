from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opentelemetry.context import Context
from opentelemetry.sdk.trace import Tracer as SDKTracer
from opentelemetry.trace import NonRecordingSpan, Span, Tracer, TracerProvider
from opentelemetry.trace.propagation import get_current_span


@dataclass
class TweakAsgiSpansTracer(Tracer):
    tracer: Tracer

    def start_span(self, name: str, context: Context | None = None, *args: Any, **kwargs: Any) -> Span:
        if name.endswith((' http send', ' http receive', ' websocket send', ' websocket receive')):
            return NonRecordingSpan(get_current_span(context).get_span_context())

        return self.tracer.start_span(name, context, *args, **kwargs)

    # This means that `with start_as_current_span(...):`
    # is roughly equivalent to `with use_span(start_span(...)):`
    start_as_current_span = SDKTracer.start_as_current_span


@dataclass
class TweakAsgiTracerProvider(TracerProvider):
    record_send_receive: bool
    tracer_provider: TracerProvider

    def get_tracer(self, *args: Any, **kwargs: Any) -> Tracer:
        tracer_provider = self.tracer_provider.get_tracer(*args, **kwargs)
        if self.record_send_receive:
            return tracer_provider
        else:
            return TweakAsgiSpansTracer(tracer_provider)
