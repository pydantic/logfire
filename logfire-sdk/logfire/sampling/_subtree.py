"""Sampling of span sub-trees below a chosen parent.

`sample_rate(rate)` records the rate and the current span in the OpenTelemetry context.
`SubtreeSampler` then makes a random keep or drop decision for each span whose parent is that span.
A dropped span is non-recording, so the delegate sampler (parent-based) drops all its descendants.
A kept span keeps its whole sub-tree.

```
parent            <- span active when `sample_rate(0.1)` is entered
├── do_action(0)  <- random decision (kept)
│   └── child     <- follows its parent (kept)
└── do_action(1)  <- random decision (dropped)
    └── child     <- follows its parent (dropped)
```
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from opentelemetry import context as context_api, trace as trace_api
from opentelemetry.sdk.trace import sampling as sdk_sampling
from opentelemetry.sdk.trace.sampling import Decision, Sampler, SamplingResult
from opentelemetry.trace import Link, SpanKind
from opentelemetry.util.types import Attributes

_SUBTREE_SAMPLING_KEY = context_api.create_key('logfire.subtree_sampling')


@dataclass(frozen=True)
class _SubtreeSampling:
    rate: float
    # `None` means that no span was active, so the decision applies to new root spans.
    anchor_span_id: int | None


@contextmanager
def sample_rate(rate: float):
    """Keep only a fraction of the span sub-trees started directly inside this block.

    Each span whose parent is the span active on entry is kept with probability `rate`.
    The descendants of each such span follow its decision, so a sub-tree is kept or dropped as a whole.

    This relies on a head sampler that follows the parent's decision, which the default samplers do.
    A head sampler that ignores the parent (for example plain `TraceIdRatioBased`) can keep spans below a
    dropped sub-tree and export them without their parent.

    Args:
        rate: The probability, from 0 to 1, of keeping each sub-tree.
    """
    if not 0 <= rate <= 1:
        raise ValueError(f'rate must be between 0 and 1, got {rate}')
    span_context = trace_api.get_current_span().get_span_context()
    anchor = span_context.span_id if span_context.is_valid else None
    token = context_api.attach(context_api.set_value(_SUBTREE_SAMPLING_KEY, _SubtreeSampling(rate, anchor)))
    try:
        yield
    finally:
        context_api.detach(token)


class SubtreeSampler(Sampler):
    """A sampler that applies `sample_rate` decisions and otherwise defers to a delegate sampler."""

    def __init__(self, delegate: Sampler | None = None) -> None:
        # `_get_from_env_or_default` is what `TracerProvider(sampler=None)` uses, so `OTEL_TRACES_SAMPLER` still applies.
        self.delegate = delegate or sdk_sampling._get_from_env_or_default()  # pyright: ignore[reportPrivateUsage]

    def should_sample(
        self,
        parent_context: context_api.Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: trace_api.TraceState | None = None,
    ) -> SamplingResult:
        delegate_result = self.delegate.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )
        if not delegate_result.decision.is_sampled():
            return delegate_result

        # The SDK passes the context explicitly given to `start_span`, or `None` for the current context.
        ctx = parent_context if parent_context is not None else context_api.get_current()
        settings = context_api.get_value(_SUBTREE_SAMPLING_KEY, ctx)
        if not isinstance(settings, _SubtreeSampling):
            return delegate_result

        parent_span_context = trace_api.get_current_span(ctx).get_span_context()
        parent_id = parent_span_context.span_id if parent_span_context.is_valid else None
        if parent_id != settings.anchor_span_id:
            return delegate_result

        # The trace ID is shared by all sub-trees in one trace, so the decision cannot be derived from it.
        if random.random() < settings.rate:
            return delegate_result
        return SamplingResult(Decision.DROP, None, delegate_result.trace_state)

    def get_description(self) -> str:
        return f'SubtreeSampler{{{self.delegate.get_description()}}}'
