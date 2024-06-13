from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from threading import Lock

from opentelemetry import context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

from logfire._internal.constants import (
    ATTRIBUTES_LOG_LEVEL_NUM_KEY,
    LEVEL_NUMBERS,
    ONE_SECOND_IN_NANOSECONDS,
    LevelName,
)
from logfire._internal.exporters.wrapper import WrapperSpanProcessor


@dataclass
class TailSamplingOptions:
    # TODO document
    level: LevelName | None = 'notice'
    duration: float | None = 1.0


@dataclass
class TraceBuffer:
    started: list[tuple[Span, context.Context | None]]
    ended: list[ReadableSpan]

    @cached_property
    def first_span(self) -> Span:
        return self.started[0][0]


class TailSamplingProcessor(WrapperSpanProcessor):
    def __init__(self, processor: SpanProcessor, options: TailSamplingOptions) -> None:
        super().__init__(processor)
        self.duration: float = (
            float('inf') if options.duration is None else options.duration * ONE_SECOND_IN_NANOSECONDS
        )
        self.level: float | int = float('inf') if options.level is None else LEVEL_NUMBERS[options.level]
        self.traces: dict[int, TraceBuffer] = {}
        self.lock = Lock()

    def on_start(self, span: Span, parent_context: context.Context | None = None) -> None:
        dropped = False
        buffer = None

        with self.lock:
            if span.context:
                trace_id = span.context.trace_id
                if span.parent is None:
                    self.traces[trace_id] = TraceBuffer([], [])

                buffer = self.traces.get(trace_id)
                if buffer is not None:
                    buffer.started.append((span, parent_context))
                    dropped = self.check_span(span, buffer)

        if buffer is None:
            super().on_start(span, parent_context)
        elif dropped:
            self.push_buffer(buffer)

    def on_end(self, span: ReadableSpan) -> None:
        dropped = False
        buffer = None

        with self.lock:
            if span.context:
                trace_id = span.context.trace_id
                buffer = self.traces.get(trace_id)
                if buffer is not None:
                    buffer.ended.append(span)
                    dropped = self.check_span(span, buffer)
                    if span.parent is None:
                        self.traces.pop(trace_id, None)

        if buffer is None:
            super().on_end(span)
        elif dropped:
            self.push_buffer(buffer)

    def check_span(self, span: ReadableSpan, buffer: TraceBuffer) -> bool:
        if (span.end_time or span.start_time or 0) - (buffer.first_span.start_time or float('inf')) > self.duration:
            self.drop_buffer(buffer)
            return True

        attributes = span.attributes or {}
        level = attributes.get(ATTRIBUTES_LOG_LEVEL_NUM_KEY)
        if not isinstance(level, int) or level >= self.level:
            self.drop_buffer(buffer)
            return True

        return False

    def drop_buffer(self, buffer: TraceBuffer) -> None:
        span_context = buffer.first_span.context
        assert span_context is not None
        del self.traces[span_context.trace_id]

    def push_buffer(self, buffer: TraceBuffer) -> None:
        for started in buffer.started:
            super().on_start(*started)
        for span in buffer.ended:
            super().on_end(span)
