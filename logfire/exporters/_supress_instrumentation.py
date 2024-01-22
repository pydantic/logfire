from __future__ import annotations

from opentelemetry import context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor


class SuppressInstrumentationProcessor(SpanProcessor):
    """Processor that suppresses instrumentation if the current context has a suppress_instrumentation.

    Intercept span creation and suppress instrumentation if the current
    context has a suppress_instrumentation value of True (that is, we are recursively creating spans
    while exporting them).
    """

    def __init__(self, processor: SpanProcessor) -> None:
        self.processor = processor

    def on_start(
        self,
        span: Span,
        parent_context: context.Context | None = None,
    ) -> None:
        if context.get_value('suppress_instrumentation'):
            return
        self.processor.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        if context.get_value('suppress_instrumentation'):
            return
        self.processor.on_end(span)

    def shutdown(self) -> None:
        self.processor.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.processor.force_flush(timeout_millis)
