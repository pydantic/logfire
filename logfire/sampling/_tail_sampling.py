from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from threading import Lock
from typing import Callable, Literal

from opentelemetry import context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.sampling import Sampler, TraceIdRatioBased
from typing_extensions import Self

from logfire._internal.constants import (
    ATTRIBUTES_LOG_LEVEL_NUM_KEY,
    LEVEL_NUMBERS,
    NUMBER_TO_LEVEL,
    ONE_SECOND_IN_NANOSECONDS,
    LevelName,
)
from logfire._internal.exporters.wrapper import WrapperSpanProcessor


@dataclass
class SpanLevel:
    """A convenience class for comparing span/log levels.

    Can be compared to log level names (strings) such as 'info' or 'error' using
    `<`, `>`, `<=`, or `>=`, so e.g. `level >= 'error'` is valid.

    Will raise an exception if compared to a non-string or an invalid level name.
    """

    number: int
    """
    The raw numeric value of the level. Higher values are more severe.
    """

    @property
    def name(self) -> LevelName | None:
        """The human-readable name of the level, or `None` if the number is invalid."""
        return NUMBER_TO_LEVEL.get(self.number)

    def __eq__(self, other: object):
        if isinstance(other, int):
            return self.number == other
        if isinstance(other, str):
            return self.name == other
        if isinstance(other, SpanLevel):
            return self.number == other.number
        return NotImplemented

    def __hash__(self):
        return hash(self.number)

    def __lt__(self, other: LevelName):
        return self.number < LEVEL_NUMBERS[other]

    def __gt__(self, other: LevelName):
        return self.number > LEVEL_NUMBERS[other]

    def __ge__(self, other: LevelName):
        return self.number >= LEVEL_NUMBERS[other]

    def __le__(self, other: LevelName):
        return self.number <= LEVEL_NUMBERS[other]


@dataclass
class TraceBuffer:
    """Arguments of `SpanProcessor.on_start` and `SpanProcessor.on_end` for spans in a single trace.

    These are stored until either the trace is included by tail sampling or it's completed and discarded.
    """

    started: list[tuple[Span, context.Context | None]]
    ended: list[ReadableSpan]

    @cached_property
    def first_span(self) -> Span:
        return self.started[0][0]

    @cached_property
    def trace_id(self) -> int:
        span_context = self.first_span.context
        assert span_context is not None
        return span_context.trace_id


@dataclass
class SpanSamplingInfo:
    """Argument passed to [`SamplingOptions`][logfire.sampling.SamplingOptions]`.tail`."""

    span: ReadableSpan
    context: context.Context | None
    event: Literal['start', 'end']
    buffer: TraceBuffer

    @property
    def level(self) -> SpanLevel:
        """The log level of the span."""
        attributes = self.span.attributes or {}
        level = attributes.get(ATTRIBUTES_LOG_LEVEL_NUM_KEY)
        if not isinstance(level, int):
            level = LEVEL_NUMBERS['info']
        return SpanLevel(level)

    @property
    def duration(self) -> float:
        """The time in seconds between the start of the trace and the start/end of this span."""
        # span.end_time and span.start_time are in nanoseconds and can be None.
        return (
            (self.span.end_time or self.span.start_time or 0) - (self.buffer.first_span.start_time or float('inf'))
        ) / ONE_SECOND_IN_NANOSECONDS


@dataclass
class SamplingOptions:
    """Options for [`logfire.configure(sampling=...)`][logfire.configure(sampling)]."""

    head: float | Sampler = 1.0
    tail: Callable[[SpanSamplingInfo], float] | None = None

    @classmethod
    def error_or_duration(
        cls,
        level_threshold: LevelName | None = 'notice',
        duration_threshold: float | None = 5.0,
        head: float | Sampler = 1.0,
        tail_sample_rate: float | None = None,
        background_rate: float = 0.0,
    ) -> Self:
        head_sample_rate = head if isinstance(head, (float, int)) else 1.0
        if tail_sample_rate is None:
            tail_sample_rate = head_sample_rate

        if not (0.0 <= background_rate <= tail_sample_rate <= head_sample_rate <= 1.0):
            raise ValueError(
                'Invalid sampling rates, must be 0.0 <= background_rate <= tail_sample_rate <= head <= 1.0'
            )

        def get_tail_sample_rate(span_info: SpanSamplingInfo) -> float:
            if duration_threshold is not None and span_info.duration > duration_threshold:
                return tail_sample_rate

            if level_threshold is not None and span_info.level >= level_threshold:
                return tail_sample_rate

            return background_rate

        return cls(head=head, tail=get_tail_sample_rate)


def check_trace_id_ratio(trace_id: int, rate: float) -> bool:
    return (trace_id & TraceIdRatioBased.TRACE_ID_LIMIT) < TraceIdRatioBased.get_bound_for_rate(rate)


class TailSamplingProcessor(WrapperSpanProcessor):
    """Passes spans to the wrapped processor if any span in a trace meets the sampling criteria."""

    def __init__(self, processor: SpanProcessor, get_tail_sample_rate: Callable[[SpanSamplingInfo], float]) -> None:
        super().__init__(processor)
        self.get_tail_sample_rate = get_tail_sample_rate

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
                if span.parent is None:
                    self.traces[trace_id] = TraceBuffer([], [])

                buffer = self.traces.get(trace_id)
                if buffer is not None:
                    # This trace's spans haven't met the criteria yet, so add this span to the buffer.
                    buffer.started.append((span, parent_context))
                    dropped = self.check_span(SpanSamplingInfo(span, parent_context, 'start', buffer))
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
                    dropped = self.check_span(SpanSamplingInfo(span, None, 'end', buffer))
                    if span.parent is None:
                        # This is the root span, so the trace is hopefully complete.
                        # Delete the buffer to save memory.
                        self.traces.pop(trace_id, None)

        if buffer is None:
            super().on_end(span)
        elif dropped:
            self.push_buffer(buffer)

    def check_span(self, span_info: SpanSamplingInfo) -> bool:
        """If the span meets the sampling criteria, drop the buffer and return True. Otherwise, return False."""
        sample_rate = self.get_tail_sample_rate(span_info)
        if sampled := check_trace_id_ratio(span_info.buffer.trace_id, sample_rate):
            self.drop_buffer(span_info.buffer)

        return sampled

    def drop_buffer(self, buffer: TraceBuffer) -> None:
        del self.traces[buffer.trace_id]

    def push_buffer(self, buffer: TraceBuffer) -> None:
        for started in buffer.started:
            super().on_start(*started)
        for span in buffer.ended:
            super().on_end(span)
