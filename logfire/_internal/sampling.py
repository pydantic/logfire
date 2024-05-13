from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from random import Random
from typing import Iterator, Sequence, cast

from opentelemetry import context as context_api, trace
from opentelemetry.sdk.trace import sampling
from opentelemetry.util.types import Attributes

from .constants import ATTRIBUTES_SAMPLE_RATE_KEY

SAMPLE_RATE = ContextVar('sample_rate', default=1.0)
SEED = ContextVar[int]('seed')


class AttributeBasedSampler(sampling.Sampler):
    def __init__(self, seed: int | None = None) -> None:
        super().__init__()
        self.random = Random(seed)

    def set_seed(self, seed: int) -> None:
        self.random.seed(seed)

    def should_sample(
        self,
        parent_context: context_api.Context | None,
        trace_id: int,
        name: str,
        kind: trace.SpanKind | None = None,
        attributes: Attributes | None = None,
        links: Sequence[trace.Link] | None = None,
        trace_state: trace.TraceState | None = None,
    ) -> sampling.SamplingResult:
        try:
            seed = SEED.get()
            random = Random(seed)
        except LookupError:
            random = self.random
        sample_rate = cast(float | None, (attributes or {}).get(ATTRIBUTES_SAMPLE_RATE_KEY))
        if sample_rate is not None:
            if random.uniform(0, 1) < sample_rate:
                decision = sampling.Decision.RECORD_AND_SAMPLE
            else:
                decision = sampling.Decision.DROP
                attributes = None
            return sampling.SamplingResult(
                decision,
                attributes,
            )
        return sampling.SamplingResult(
            sampling.Decision.RECORD_AND_SAMPLE,
            attributes,
        )

    def get_description(self) -> str:
        return self.__class__.__name__


@contextmanager
def sample(rate: float) -> Iterator[None]:
    if rate < 0 or rate > 1:
        raise ValueError('Sample rate must be between 0 and 1')
    token = SAMPLE_RATE.set(rate)
    try:
        yield
    finally:
        SAMPLE_RATE.reset(token)


@contextmanager
def seed(seed: int) -> Iterator[None]:
    """Used for testing purposes to ensure reproducibility."""
    token = SEED.set(seed)
    try:
        yield
    finally:
        SEED.reset(token)
