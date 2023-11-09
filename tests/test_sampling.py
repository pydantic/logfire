import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import logfire
from logfire.testing import SeededRandomIdGenerator, TestExporter


@pytest.mark.parametrize('sample_rate', [-1, 1.5])
def test_invalid_sample_rate(sample_rate: float) -> None:
    with pytest.raises(ValueError, match='sample_rate must be between 0 and 1'):
        logfire.with_trace_sample_rate(sample_rate)


def test_sample_rate_config() -> None:
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        trace_sample_rate=0.1,
        processors=[SimpleSpanProcessor(exporter)],
        id_generator=SeededRandomIdGenerator(),
    )

    for _ in range(100):
        with logfire.span('test'):
            with logfire.span('inner'):
                pass

    assert len(exporter.exported_spans_as_dict()) == 30


def test_sampling_override() -> None:
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        trace_sample_rate=1,
        id_generator=SeededRandomIdGenerator(),
        processors=[SimpleSpanProcessor(exporter)],
    )

    sampled = logfire.with_trace_sample_rate(0.1)

    for _ in range(100):
        with sampled.span('outer'):
            with logfire.span('inner'):
                pass

    assert len(exporter.exported_spans_as_dict()) == 30


def test_child_spans_dropped_override() -> None:
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        trace_sample_rate=1,
        id_generator=SeededRandomIdGenerator(),
        processors=[SimpleSpanProcessor(exporter)],
    )

    sampled = logfire.with_trace_sample_rate(0)

    with sampled.span('outer'):
        # create many inner spans
        for _ in range(100):
            with logfire.span('inner'):
                pass

    assert len(exporter.exported_spans_as_dict()) == 0
