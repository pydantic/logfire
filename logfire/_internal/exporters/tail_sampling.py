from __future__ import annotations

import random
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
    level: LevelName | None = 'notice'
    """
    Include all spans/logs with level greater than or equal to this level.
    If None, spans are not included based on level.
    """

    duration: float | None = 1.0
    """
    Include all spans/logs with duration greater than this duration in seconds.
    If None, spans are not included based on duration.
    """


@dataclass
class TraceBuffer:
    """Arguments of `on_start` and `on_end` for spans in a single trace."""

    started: list[tuple[Span, context.Context | None]]
    ended: list[ReadableSpan]

    @cached_property
    def first_span(self) -> Span:
        return self.started[0][0]


class TailSamplingProcessor(WrapperSpanProcessor):
    """Passes spans to the wrapped processor if any span in a trace meets the sampling criteria."""

    def __init__(self, processor: SpanProcessor, options: TailSamplingOptions, random_rate: float) -> None:
        super().__init__(processor)
        self.duration: float = (
            float('inf') if options.duration is None else options.duration * ONE_SECOND_IN_NANOSECONDS
        )
        self.level: float | int = float('inf') if options.level is None else LEVEL_NUMBERS[options.level]
        self.random_rate = random_rate

        # A TraceBuffer is typically created for each new trace.
        # If a span meets the sampling criteria, the buffer is dropped and all spans within are pushed
        # to the wrapped processor.
        # So when more spans arrive and there's no buffer, they get passed through immediately.
        self.traces: dict[int, TraceBuffer] = {}

        # Code that touches self.traces and its contents should be protected by this lock.
        self.lock = Lock()

    def on_start(self, span: Span, parent_context: context.Context | None = None) -> None:
        dropped = False
        buffer = None

        with self.lock:
            # span.context could supposedly be None, not sure how.
            if span.context:  # pragma: no branch
                trace_id = span.context.trace_id
                # If span.parent is None, it's the root span of a trace.
                # If random.random() <= self.random_rate, immediately include this trace,
                # meaning no buffer for it.
                if span.parent is None and random.random() > self.random_rate:
                    self.traces[trace_id] = TraceBuffer([], [])

                buffer = self.traces.get(trace_id)
                if buffer is not None:
                    # This trace's spans haven't met the criteria yet, so add this span to the buffer.
                    buffer.started.append((span, parent_context))
                    dropped = self.check_span(span, buffer)
                # The opposite case is handled outside the lock since it may take some time.

        # This code may take longer since it calls the wrapped processor which might do anything.
        # It shouldn't be inside the lock to avoid blocking other threads.
        # Since it's not in the lock, it shouldn't touch self.traces or its contents.
        if buffer is None:
            super().on_start(span, parent_context)
        elif dropped:
            self.push_buffer(buffer)

    def on_end(self, span: ReadableSpan) -> None:
        # This has a very similar structure and reasoning to on_start.

        dropped = False
        buffer = None

        with self.lock:
            if span.context:  # pragma: no branch
                trace_id = span.context.trace_id
                buffer = self.traces.get(trace_id)
                if buffer is not None:
                    buffer.ended.append(span)
                    dropped = self.check_span(span, buffer)
                    if span.parent is None:
                        # This is the root span, so the trace is hopefully complete.
                        # Delete the buffer to save memory.
                        self.traces.pop(trace_id, None)

        if buffer is None:
            super().on_end(span)
        elif dropped:
            self.push_buffer(buffer)

    def check_span(self, span: ReadableSpan, buffer: TraceBuffer) -> bool:
        """If the span meets the sampling criteria, drop the buffer and return True. Otherwise, return False."""
        # span.end_time and span.start_time are in nanoseconds and can be None.
        if (span.end_time or span.start_time or 0) - (buffer.first_span.start_time or float('inf')) > self.duration:
            self.drop_buffer(buffer)
            return True

        attributes = span.attributes or {}
        level = attributes.get(ATTRIBUTES_LOG_LEVEL_NUM_KEY)
        if not isinstance(level, int):
            level = LEVEL_NUMBERS['info']
        if level >= self.level:
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
