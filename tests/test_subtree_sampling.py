from __future__ import annotations

import random
from typing import Any

import pytest
from opentelemetry.sdk.trace.sampling import ALWAYS_ON

import logfire
from logfire.sampling import SubtreeSampler
from logfire.testing import TestExporter


def test_sample_rate_keeps_whole_subtrees(exporter: TestExporter) -> None:
    random.seed(0)
    with logfire.span('parent'):
        with logfire.sample_rate(0.1):
            for v in range(1000):
                with logfire.span('action {v}', v=v):
                    logfire.info('inner {v}', v=v)
        logfire.info('after')

    spans = exporter.exported_spans
    names = [s.name for s in spans]
    assert 'parent' in names
    assert 'after' in names

    kept_actions = {s.attributes.get('v') for s in spans if s.name == 'action {v}' and s.attributes}  # type: ignore[reportUnhashable]
    kept_inner = {s.attributes.get('v') for s in spans if s.name == 'inner {v}' and s.attributes}  # type: ignore[reportUnhashable]
    # Each sub-tree is kept or dropped as a whole.
    assert kept_actions == kept_inner
    assert 60 < len(kept_actions) < 140


def test_otel_traces_sampler_env_still_applies(
    exporter: TestExporter, config_kwargs: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('OTEL_TRACES_SAMPLER', 'always_off')
    logfire.configure(**config_kwargs)
    with logfire.span('span'):
        logfire.info('log')
    assert exporter.exported_spans == []


@pytest.mark.parametrize('rate', [0.0, 1.0])
def test_sample_rate_bounds(exporter: TestExporter, rate: float) -> None:
    with logfire.span('parent'):
        with logfire.sample_rate(rate):
            for v in range(20):
                logfire.info('log {v}', v=v)
    logs = [s for s in exporter.exported_spans if s.name == 'log {v}']
    assert len(logs) == 20 * rate


def test_sample_rate_validates() -> None:
    with pytest.raises(ValueError):
        with logfire.sample_rate(1.5):
            pass  # pragma: no cover


def test_subtree_sampler_description() -> None:
    assert SubtreeSampler(ALWAYS_ON).get_description() == 'SubtreeSampler{AlwaysOnSampler}'
