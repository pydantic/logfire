from __future__ import annotations

from typing import Sequence, cast

from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, Decision, ParentBased, Sampler, SamplingResult
from opentelemetry.trace import Link, SpanContext, SpanKind, get_current_span
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes

from ._constants import ATTRIBUTES_SAMPLE_RATE_KEY


def _get_parent_trace_state(parent_context: Context) -> TraceState | None:
    parent_span_context = cast('SpanContext | None', get_current_span(parent_context).get_span_context())
    if parent_span_context is None or not parent_span_context.is_valid:
        return None
    return parent_span_context.trace_state


class AttributeBasedSampler(Sampler):
    """OTEL sampler that samples traces based on a sample rate.

    This uses `logfire.sample_rate` attribute if present to set the sampling rate otherwise falls back
    to the same behavior as OTEL's TraceIdRatioBased sampler.
    """

    def __init__(self, sample_rate: float = 1.0) -> None:
        if sample_rate > 1 or sample_rate < 0:
            raise ValueError('sample_rate must be between 0 and 1')
        self.sample_rate = sample_rate

    # For compatibility with 64 bit trace IDs, the sampler checks the 64
    # low-order bits of the trace ID to decide whether to sample a given trace.
    TRACE_ID_LIMIT = (1 << 64) - 1

    @classmethod
    def get_bound_for_rate(cls, rate: float) -> int:
        return round(rate * (cls.TRACE_ID_LIMIT + 1))

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        # For compatibility with 64 bit trace IDs, the sampler checks the 64
        # low-order bits of the trace ID to decide whether to sample a given trace.
        trace_id_limit = (1 << 64) - 1

        rate = self.sample_rate

        if attributes:
            sample_rate = attributes.get(ATTRIBUTES_SAMPLE_RATE_KEY)
            if sample_rate is not None:
                rate = cast(float, sample_rate)

        bound = round(rate * (trace_id_limit + 1))

        decision = Decision.DROP
        if trace_id & self.TRACE_ID_LIMIT < bound:
            decision = Decision.RECORD_AND_SAMPLE
        if decision is Decision.DROP:
            attributes = None
        return SamplingResult(
            decision,
            attributes,
            _get_parent_trace_state(parent_context) if parent_context else None,  # type: ignore
        )

    def get_description(self) -> str:
        return f'AttributeBasedSampler{{{self.sample_rate}}}'


class LogfireSampler(Sampler):
    """Default sampler for Logfire.

    This sampler mimics the defaults for the OTEL SDK but uses `AttributeBasedSampler` instead of `TraceIdRatioBased`
    to support the `logfire.sample_rate` attribute.
    """

    def __init__(
        self,
        sample_rate: float = 1.0,
    ) -> None:
        # note: use a sample rate of 1 if the parent was sampled
        # to include all of it's children _unless_ the `logfire.sample_rate` attribute is set
        self.sampler = ParentBased(
            root=AttributeBasedSampler(sample_rate=sample_rate),
            remote_parent_sampled=AttributeBasedSampler(sample_rate=1),
            remote_parent_not_sampled=ALWAYS_OFF,
            local_parent_sampled=AttributeBasedSampler(sample_rate=1),
            local_parent_not_sampled=ALWAYS_OFF,
        )

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        return self.sampler.should_sample(
            parent_context,
            trace_id,
            name,
            kind,  # type: ignore
            attributes,
            links,  # type: ignore
            trace_state,  # type: ignore
        )

    def get_description(self) -> str:
        return f'LogfireSampler{{{self.sampler}}}'
