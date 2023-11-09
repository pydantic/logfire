import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import logfire
from logfire.testing import SeededRandomIdGenerator, TestExporter, TimeGenerator


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


def test_with_sample_rate_context_manager() -> None:
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        trace_sample_rate=1,
        id_generator=SeededRandomIdGenerator(),
        ns_timestamp_generator=TimeGenerator(),
        processors=[SimpleSpanProcessor(exporter)],
    )

    with logfire.with_trace_sample_rate(0) as sampled:
        with logfire.span('1'):
            with logfire.span('2'):
                pass

    with logfire.span('3'):
        with logfire.span('4'):
            with sampled.span('5'):
                pass

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': '4',
            'context': {'trace_id': 746805015404516437, 'span_id': 2195908194, 'is_remote': False},
            'parent': {'trace_id': 746805015404516437, 'span_id': 1112038970, 'is_remote': False},
            'start_time': 4000000000,
            'end_time': 6000000000,
            'attributes': {
                'code.filepath': 'test_sampling.py',
                'code.lineno': 123,
                'code.function': 'test_with_sample_rate_context_manager',
                'logfire.msg_template': '4',
                'logfire.span_type': 'span',
                'logfire.msg': '4',
            },
        },
        {
            'name': '3',
            'context': {'trace_id': 746805015404516437, 'span_id': 1112038970, 'is_remote': False},
            'parent': None,
            'start_time': 3000000000,
            'end_time': 7000000000,
            'attributes': {
                'code.filepath': 'test_sampling.py',
                'code.lineno': 123,
                'code.function': 'test_with_sample_rate_context_manager',
                'logfire.msg_template': '3',
                'logfire.span_type': 'span',
                'logfire.msg': '3',
            },
        },
    ]
