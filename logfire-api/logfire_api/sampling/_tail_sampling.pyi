from _typeshed import Incomplete
from dataclasses import dataclass
from functools import cached_property
from logfire._internal.constants import ATTRIBUTES_LOG_LEVEL_NUM_KEY as ATTRIBUTES_LOG_LEVEL_NUM_KEY, LEVEL_NUMBERS as LEVEL_NUMBERS, LevelName as LevelName, NUMBER_TO_LEVEL as NUMBER_TO_LEVEL, ONE_SECOND_IN_NANOSECONDS as ONE_SECOND_IN_NANOSECONDS
from logfire._internal.exporters.wrapper import WrapperSpanProcessor as WrapperSpanProcessor
from opentelemetry import context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.sampling import Sampler
from typing import Callable, Literal
from typing_extensions import Self

@dataclass
class SpanLevel:
    """A convenience class for comparing span levels."""
    number: int
    @property
    def name(self) -> LevelName | None:
        """The human-readable name of the level, or None if the number is invalid."""
    def __eq__(self, other: object): ...
    def __lt__(self, other: LevelName): ...
    def __gt__(self, other: LevelName): ...
    def __ge__(self, other: LevelName): ...
    def __le__(self, other: LevelName): ...

@dataclass
class TraceBuffer:
    """Arguments of `on_start` and `on_end` for spans in a single trace."""
    started: list[tuple[Span, context.Context | None]]
    ended: list[ReadableSpan]
    @cached_property
    def first_span(self) -> Span: ...
    @cached_property
    def trace_id(self) -> int: ...

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
    @property
    def duration(self) -> float:
        """The time in seconds between the start of the trace and the start/end of this span."""

@dataclass
class SamplingOptions:
    """Options for [`logfire.configure(sampling=...)`][logfire.configure(sampling)]."""
    head: float | Sampler = ...
    tail: Callable[[SpanSamplingInfo], float] | None = ...
    @classmethod
    def error_or_duration(cls, level_threshold: LevelName | None = 'notice', duration_threshold: float | None = 5.0, head: float | Sampler = 1.0, tail_sample_rate: float | None = None, background_rate: float = 0.0) -> Self: ...

def check_trace_id_ratio(trace_id: int, rate: float) -> bool: ...

class TailSamplingProcessor(WrapperSpanProcessor):
    """Passes spans to the wrapped processor if any span in a trace meets the sampling criteria."""
    get_tail_sample_rate: Incomplete
    traces: Incomplete
    lock: Incomplete
    def __init__(self, processor: SpanProcessor, get_tail_sample_rate: Callable[[SpanSamplingInfo], float]) -> None: ...
    def on_start(self, span: Span, parent_context: context.Context | None = None) -> None: ...
    def on_end(self, span: ReadableSpan) -> None: ...
    def check_span(self, span_info: SpanSamplingInfo) -> bool:
        """If the span meets the sampling criteria, drop the buffer and return True. Otherwise, return False."""
    def drop_buffer(self, buffer: TraceBuffer) -> None: ...
    def push_buffer(self, buffer: TraceBuffer) -> None: ...
