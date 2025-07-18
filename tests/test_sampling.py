from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import pytest
from inline_snapshot import snapshot
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import logfire
from logfire.testing import SeededRandomIdGenerator, TestExporter


@dataclass
class SpanNode:
    name: str | None = None
    children: list[SpanNode] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


# TODO(Marcelo): Remove pragma when this file is covered by tests.
def build_tree(exported_spans: list[dict[str, Any]]) -> list[SpanNode]:  # pragma: no cover
    traces: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for span in exported_spans:
        trace_id: int = span['context']['trace_id']
        traces[trace_id].append(span)

    roots: list[SpanNode] = []
    tree: dict[int, dict[int, SpanNode]] = {}
    for trace_id, trace in traces.items():
        spans: dict[int, SpanNode] = {}
        tree[trace_id] = spans
        for span in trace:
            span_id: int = span['context']['span_id']
            spans[span_id] = SpanNode(name=span['name'])
            if span['parent'] is None:
                roots.append(spans[span_id])
    for trace_id, trace in traces.items():
        spans = tree[trace_id]
        for span in trace:
            span_id: int = span['context']['span_id']
            parent_id: int | None = span['parent']['span_id'] if span['parent'] is not None else None
            if parent_id is not None:
                spans[parent_id].children.append(spans[span_id])

    return roots


@pytest.mark.skipif(
    not hasattr(logfire, 'with_trace_sample_rate'), reason='with_trace_sample_rate is hidden from public API'
)
@pytest.mark.parametrize('sample_rate', [-1, 1.5])
def test_invalid_sample_rate(sample_rate: float) -> None:  # pragma: no cover
    with pytest.raises(ValueError, match='sample_rate must be between 0 and 1'):
        logfire.DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate(sample_rate)


def test_sample_rate_config(exporter: TestExporter, config_kwargs: dict[str, Any]) -> None:
    config_kwargs.update(
        sampling=logfire.SamplingOptions(head=0.3),
        advanced=logfire.AdvancedOptions(id_generator=SeededRandomIdGenerator()),
    )
    logfire.configure(**config_kwargs)

    for _ in range(1000):
        with logfire.span('outer'):
            with logfire.span('inner'):
                pass

    # 1000 iterations of 2 spans -> 2000 spans
    # 30% sampling -> 600 spans (approximately)
    assert len(exporter.exported_spans_as_dict()) == 588, len(exporter.exported_spans_as_dict())


@pytest.mark.skipif(
    not hasattr(logfire, 'with_trace_sample_rate'), reason='with_trace_sample_rate is hidden from public API'
)
def test_sample_rate_runtime() -> None:  # pragma: no cover
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        advanced=logfire.AdvancedOptions(id_generator=SeededRandomIdGenerator()),
        metrics=logfire.MetricsOptions(additional_readers=[InMemoryMetricReader()]),
    )

    for _ in range(100):
        with logfire.DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate(0.5).span('outer'):
            with logfire.span('inner'):
                pass

    # 100 iterations of 2 spans -> 200 spans
    # 50% sampling -> 100 spans (approximately)
    assert len(exporter.exported_spans_as_dict()) == 102


@pytest.mark.skipif(
    not hasattr(logfire, 'with_trace_sample_rate'), reason='with_trace_sample_rate is hidden from public API'
)
def test_outer_sampled_inner_not() -> None:  # pragma: no cover
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        advanced=logfire.AdvancedOptions(id_generator=SeededRandomIdGenerator()),
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        metrics=logfire.MetricsOptions(additional_readers=[InMemoryMetricReader()]),
    )

    for _ in range(10):
        with logfire.DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate(0.1).span('1'):
            with logfire.span('2'):
                with logfire.span('3'):
                    pass

    assert build_tree(exporter.exported_spans_as_dict()) == snapshot(
        [
            SpanNode(name='1', children=[SpanNode(name='2', children=[SpanNode(name='3', children=[])])]),
            SpanNode(name='1', children=[SpanNode(name='2', children=[SpanNode(name='3', children=[])])]),
        ]
    )


@pytest.mark.skipif(
    not hasattr(logfire, 'with_trace_sample_rate'), reason='with_trace_sample_rate is hidden from public API'
)
def test_outer_and_inner_sampled() -> None:  # pragma: no cover
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        advanced=logfire.AdvancedOptions(id_generator=SeededRandomIdGenerator()),
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        metrics=logfire.MetricsOptions(additional_readers=[InMemoryMetricReader()]),
    )

    for _ in range(10):
        with logfire.DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate(0.75).span('1'):
            with logfire.DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate(0.75).span('2'):
                with logfire.DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate(0.75).span('3'):
                    pass

    assert build_tree(exporter.exported_spans_as_dict()) == snapshot(
        [
            SpanNode(name='1', children=[SpanNode(name='2', children=[])]),
            SpanNode(name='1', children=[SpanNode(name='2', children=[SpanNode(name='3', children=[])])]),
            SpanNode(name='1', children=[SpanNode(name='2', children=[SpanNode(name='3', children=[])])]),
            SpanNode(name='1', children=[SpanNode(name='2', children=[SpanNode(name='3', children=[])])]),
            SpanNode(name='1', children=[SpanNode(name='2', children=[SpanNode(name='3', children=[])])]),
            SpanNode(name='1', children=[]),
            SpanNode(name='1', children=[SpanNode(name='2', children=[SpanNode(name='3', children=[])])]),
            SpanNode(name='1', children=[SpanNode(name='2', children=[SpanNode(name='3', children=[])])]),
        ]
    )


@pytest.mark.skipif(
    not hasattr(logfire, 'with_trace_sample_rate'), reason='with_trace_sample_rate is hidden from public API'
)
def test_sampling_rate_does_not_get_overwritten() -> None:  # pragma: no cover
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        advanced=logfire.AdvancedOptions(id_generator=SeededRandomIdGenerator()),
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        metrics=logfire.MetricsOptions(additional_readers=[InMemoryMetricReader()]),
    )

    for _ in range(10):
        with logfire.DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate(0).span('1'):
            for _ in range(100):
                with logfire.DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate(1).span('2'):
                    pass

    assert build_tree(exporter.exported_spans_as_dict()) == snapshot([])
