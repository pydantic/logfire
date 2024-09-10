"""Types for configuring sampling."""

from ._tail_sampling import SamplingOptions, SpanLevel, TailSamplingSpanInfo

__all__ = [
    'SamplingOptions',
    'SpanLevel',
    'TailSamplingSpanInfo',
]
