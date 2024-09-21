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
    """A convenience class for comparing span/log levels.

    Can be compared to log level names (strings) such as 'info' or 'error' using
    `<`, `>`, `<=`, or `>=`, so e.g. `level >= 'error'` is valid.

    Will raise an exception if compared to a non-string or an invalid level name.
    """
    number: int
    @property
    def name(self) -> LevelName | None:
        """The human-readable name of the level, or `None` if the number is invalid."""
    def __eq__(self, other: object): ...
    def __hash__(self): ...
    def __lt__(self, other: LevelName): ...
    def __gt__(self, other: LevelName): ...
    def __ge__(self, other: LevelName): ...
    def __le__(self, other: LevelName): ...

@dataclass
class TraceBuffer:
    """Arguments of `SpanProcessor.on_start` and `SpanProcessor.on_end` for spans in a single trace.

    These are stored until either the trace is included by tail sampling or it's completed and discarded.
    """
    started: list[tuple[Span, context.Context | None]]
    ended: list[ReadableSpan]
    @cached_property
    def first_span(self) -> Span: ...
    @cached_property
    def trace_id(self) -> int: ...

@dataclass
class TailSamplingSpanInfo:
    """Argument passed to the [`SamplingOptions.tail`][logfire.sampling.SamplingOptions.tail] callback."""
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
    """Options for [`logfire.configure(sampling=...)`][logfire.configure(sampling)].

    See the [sampling guide](https://logfire.pydantic.dev/docs/guides/advanced/sampling/).
    """
    head: float | Sampler = ...
    tail: Callable[[TailSamplingSpanInfo], float] | None = ...
    @classmethod
    def level_or_duration(cls, *, head: float | Sampler = 1.0, level_threshold: LevelName | None = 'notice', duration_threshold: float | None = 5.0, background_rate: float = 0.0) -> Self:
        """Returns a `SamplingOptions` instance that tail samples traces based on their log level and duration.

        If a trace has at least one span/log that has a log level greater than or equal to `level_threshold`,
        or if the duration of the whole trace is greater than `duration_threshold` seconds,
        then the whole trace will be included.
        Otherwise, the probability is `background_rate`.

        The `head` parameter is the same as in the `SamplingOptions` constructor.
        """

def check_trace_id_ratio(trace_id: int, rate: float) -> bool: ...

class TailSamplingProcessor(WrapperSpanProcessor):
    """Passes spans to the wrapped processor if any span in a trace meets the sampling criteria."""
    get_tail_sample_rate: Incomplete
    traces: Incomplete
    lock: Incomplete
    def __init__(self, processor: SpanProcessor, get_tail_sample_rate: Callable[[TailSamplingSpanInfo], float]) -> None: ...
    def on_start(self, span: Span, parent_context: context.Context | None = None) -> None: ...
    def on_end(self, span: ReadableSpan) -> None: ...
    def check_span(self, span_info: TailSamplingSpanInfo) -> bool:
        """If the span meets the sampling criteria, drop the buffer and return True. Otherwise, return False."""
    def drop_buffer(self, buffer: TraceBuffer) -> None: ...
    def push_buffer(self, buffer: TraceBuffer) -> None: ...
