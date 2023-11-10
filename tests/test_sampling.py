from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import logfire
from logfire.testing import SeededRandomIdGenerator, TestExporter, TimeGenerator


@dataclass
class SpanNode:
    name: str | None = None
    children: list[SpanNode] = field(default_factory=list)


def build_tree(exported_spans: list[dict[str, Any]]) -> list[SpanNode]:
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


@pytest.mark.parametrize('sample_rate', [-1, 1.5])
def test_invalid_sample_rate(sample_rate: float) -> None:
    with pytest.raises(ValueError, match='sample_rate must be between 0 and 1'):
        logfire.with_trace_sample_rate(sample_rate)


def test_sample_rate_config() -> None:
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        trace_sample_rate=0.05,
        processors=[SimpleSpanProcessor(exporter)],
        id_generator=SeededRandomIdGenerator(),
    )

    for _ in range(100):
        with logfire.span('outer'):
            with logfire.span('inner'):
                pass

    # 100 iterations of 2 spans -> 200 spans
    # 5% sampling -> 10 spans (approximately)
    assert len(exporter.exported_spans_as_dict()) == 6


def test_sample_rate_runtime() -> None:
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        trace_sample_rate=1,
        processors=[SimpleSpanProcessor(exporter)],
        id_generator=SeededRandomIdGenerator(),
    )

    for _ in range(100):
        with logfire.with_trace_sample_rate(0.05).span('outer'):
            with logfire.span('inner'):
                pass

    # 100 iterations of 2 spans -> 200 spans
    # 5% sampling -> 10 spans (approximately)
    assert len(exporter.exported_spans_as_dict()) == 12


def test_outer_sampled_inner_not() -> None:
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        trace_sample_rate=1,
        id_generator=SeededRandomIdGenerator(),
        ns_timestamp_generator=TimeGenerator(),
        processors=[SimpleSpanProcessor(exporter)],
    )

    for _ in range(10):
        with logfire.with_trace_sample_rate(0.1).span('1'):
            with logfire.span('2'):
                with logfire.span('3'):
                    pass

    # insert_assert(build_tree(exporter.exported_spans_as_dict()))
    assert build_tree(exporter.exported_spans_as_dict()) == [
        SpanNode(name='1', children=[SpanNode(name='2', children=[SpanNode(name='3', children=[])])])
    ]


def test_outer_and_inner_sampled() -> None:
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        trace_sample_rate=1,
        id_generator=SeededRandomIdGenerator(),
        ns_timestamp_generator=TimeGenerator(),
        processors=[SimpleSpanProcessor(exporter)],
    )

    for _ in range(10):
        with logfire.with_trace_sample_rate(0.75).span('1'):
            with logfire.with_trace_sample_rate(0.75).span('2'):
                with logfire.with_trace_sample_rate(0.75).span('3'):
                    pass

    # insert_assert(build_tree(exporter.exported_spans_as_dict()))
    assert build_tree(exporter.exported_spans_as_dict()) == [
        SpanNode(name='1', children=[SpanNode(name='2', children=[])]),
        SpanNode(name='1', children=[SpanNode(name='2', children=[])]),
        SpanNode(name='1', children=[SpanNode(name='2', children=[])]),
        SpanNode(name='1', children=[SpanNode(name='2', children=[SpanNode(name='3', children=[])])]),
        SpanNode(name='1', children=[SpanNode(name='2', children=[SpanNode(name='3', children=[])])]),
    ]


def test_sampling_rate_does_not_get_overwritten() -> None:
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        trace_sample_rate=1,
        id_generator=SeededRandomIdGenerator(),
        ns_timestamp_generator=TimeGenerator(),
        processors=[SimpleSpanProcessor(exporter)],
    )

    for _ in range(10):
        with logfire.with_trace_sample_rate(0).span('1'):
            for _ in range(100):
                with logfire.with_trace_sample_rate(1).span('2'):
                    pass

    # insert_assert(build_tree(exporter.exported_spans_as_dict()))
    assert build_tree(exporter.exported_spans_as_dict()) == []
