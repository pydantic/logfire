"""Types for configuring sampling. See the [sampling guide](https://docs.pydantic.dev/logfire/guides/advanced/sampling/)."""

from ._tail_sampling import SamplingOptions, SpanLevel, TailSamplingSpanInfo

__all__ = [
    'SamplingOptions',
    'SpanLevel',
    'TailSamplingSpanInfo',
]
