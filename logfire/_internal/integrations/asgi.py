from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opentelemetry.context import Context
from opentelemetry.sdk.trace import Tracer as SDKTracer
from opentelemetry.trace import NonRecordingSpan, Span, SpanKind, Tracer, TracerProvider
from opentelemetry.trace.propagation import get_current_span
from opentelemetry.util import types

from logfire._internal.constants import log_level_attributes


@dataclass
class TweakAsgiSpansTracer(Tracer):
    record_send_receive: bool
    tracer: Tracer

    def start_span(
        self,
        name: str,
        context: Context | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: types.Attributes = None,
        *args: Any,
        **kwargs: Any,
    ) -> Span:
        if name.endswith((' http send', ' http receive', ' websocket send', ' websocket receive')):
            if self.record_send_receive:
                attributes = {**log_level_attributes('debug'), **(attributes or {})}
            else:
                return NonRecordingSpan(get_current_span(context).get_span_context())

        return self.tracer.start_span(name, context, kind, attributes, *args, **kwargs)

    # This means that `with start_as_current_span(...):`
    # is roughly equivalent to `with use_span(start_span(...)):`
    start_as_current_span = SDKTracer.start_as_current_span


@dataclass
class TweakAsgiTracerProvider(TracerProvider):
    record_send_receive: bool
    tracer_provider: TracerProvider

    def get_tracer(self, *args: Any, **kwargs: Any) -> Tracer:
        return TweakAsgiSpansTracer(self.record_send_receive, self.tracer_provider.get_tracer(*args, **kwargs))
