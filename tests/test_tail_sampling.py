from __future__ import annotations

from typing import Any

from inline_snapshot import snapshot

import logfire
from logfire.sampling import SpanSamplingInfo
from logfire.testing import SeededRandomIdGenerator, TestExporter


def test_level_threshold(config_kwargs: dict[str, Any], exporter: TestExporter):
    # Use the default TailSamplingOptions.level of 'notice'.
    # Set duration to None to not include spans with a long duration.
    logfire.configure(**config_kwargs, sampling=logfire.SamplingOptions.error_or_duration(duration_threshold=None))

    with logfire.span('ignored span'):
        logfire.debug('ignored debug')
    logfire.notice('notice')
    with logfire.span('ignored span'):
        logfire.info('ignored info')
    logfire.warn('warn')

    # Include this whole tree because of the inner error
    with logfire.span('span'):
        with logfire.span('span2'):
            logfire.error('error')

    # Include this whole tree because of the outer fatal
    with logfire.span('span3', _level='fatal'):
        logfire.trace('trace')

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'notice',
                'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
                'parent': None,
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 10,
                    'logfire.msg_template': 'notice',
                    'logfire.msg': 'notice',
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_sampling',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'warn',
                'context': {'trace_id': 4, 'span_id': 8, 'is_remote': False},
                'parent': None,
                'start_time': 8000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'warn',
                    'logfire.msg': 'warn',
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_sampling',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'span (pending)',
                'context': {'trace_id': 5, 'span_id': 10, 'is_remote': False},
                'parent': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'start_time': 9000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_sampling',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'span2 (pending)',
                'context': {'trace_id': 5, 'span_id': 12, 'is_remote': False},
                'parent': {'trace_id': 5, 'span_id': 11, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_sampling',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span2',
                    'logfire.msg': 'span2',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000009',
                },
            },
            {
                'name': 'error',
                'context': {'trace_id': 5, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 5, 'span_id': 11, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 11000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'error',
                    'logfire.msg': 'error',
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_sampling',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'span2',
                'context': {'trace_id': 5, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 12000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_sampling',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span2',
                    'logfire.msg': 'span2',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'span',
                'context': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 13000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_sampling',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'span3 (pending)',
                'context': {'trace_id': 6, 'span_id': 15, 'is_remote': False},
                'parent': {'trace_id': 6, 'span_id': 14, 'is_remote': False},
                'start_time': 14000000000,
                'end_time': 14000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_sampling',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span3',
                    'logfire.msg': 'span3',
                    'logfire.level_num': 21,
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'trace',
                'context': {'trace_id': 6, 'span_id': 16, 'is_remote': False},
                'parent': {'trace_id': 6, 'span_id': 14, 'is_remote': False},
                'start_time': 15000000000,
                'end_time': 15000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 1,
                    'logfire.msg_template': 'trace',
                    'logfire.msg': 'trace',
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_sampling',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'span3',
                'context': {'trace_id': 6, 'span_id': 14, 'is_remote': False},
                'parent': None,
                'start_time': 14000000000,
                'end_time': 16000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_sampling',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span3',
                    'logfire.msg': 'span3',
                    'logfire.level_num': 21,
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_duration_threshold(config_kwargs: dict[str, Any], exporter: TestExporter):
    # Set level to None to not include spans merely based on a high level.
    logfire.configure(
        **config_kwargs, sampling=logfire.SamplingOptions.error_or_duration(level_threshold=None, duration_threshold=3)
    )

    logfire.error('short1')
    with logfire.span('span'):
        logfire.error('short2')

    # This has a total fake duration of 3s, which doesn't get included because we use >, not >=.
    with logfire.span('span2'):
        with logfire.span('span3', _level='error'):
            pass

    # This has a total fake duration of 4s, which does get included.
    with logfire.span('span4'):
        with logfire.span('span5'):
            logfire.info('long1')

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'span4 (pending)',
                'context': {'trace_id': 4, 'span_id': 10, 'is_remote': False},
                'parent': {'trace_id': 4, 'span_id': 9, 'is_remote': False},
                'start_time': 9000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_duration_sampling',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span4',
                    'logfire.msg': 'span4',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'span5 (pending)',
                'context': {'trace_id': 4, 'span_id': 12, 'is_remote': False},
                'parent': {'trace_id': 4, 'span_id': 11, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_duration_sampling',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span5',
                    'logfire.msg': 'span5',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000009',
                },
            },
            {
                'name': 'long1',
                'context': {'trace_id': 4, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 4, 'span_id': 11, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 11000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'long1',
                    'logfire.msg': 'long1',
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_duration_sampling',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'span5',
                'context': {'trace_id': 4, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 4, 'span_id': 9, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 12000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_duration_sampling',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span5',
                    'logfire.msg': 'span5',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'span4',
                'context': {'trace_id': 4, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 13000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_duration_sampling',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span4',
                    'logfire.msg': 'span4',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_background_rate(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs.update(
        sampling=logfire.SamplingOptions.error_or_duration(background_rate=0.3),
        id_generator=SeededRandomIdGenerator(seed=1),
    )
    logfire.configure(**config_kwargs)
    # These spans should all be included because the level is above the default.
    for _ in range(100):
        logfire.error('error')
    assert len(exporter.exported_spans) == 100

    # About 30% these spans (i.e. an extra ~300) should be included because of the trace_sample_rate.
    # None of them meet the tail sampling criteria.
    for _ in range(1000):
        logfire.info('info')
    assert len(exporter.exported_spans) == 100 + 321


def test_custom_head_and_tail(config_kwargs: dict[str, Any], exporter: TestExporter):
    span_counts = {'start': 0, 'end': 0}

    def get_tail_sample_rate(span_info: SpanSamplingInfo) -> float:
        span_counts[span_info.event] += 1
        if span_info.duration >= 1:
            return 0.5
        if span_info.level > 'warn':
            return 0.3
        return 0.1

    config_kwargs.update(
        trace_sample_rate=0.7,  # TODO remove in favor of head_sample_rate
        sampling=logfire.SamplingOptions(
            head_sample_rate=0.7,
            get_tail_sample_rate=get_tail_sample_rate,
        ),
        id_generator=SeededRandomIdGenerator(seed=3),
    )

    logfire.configure(**config_kwargs)

    for _ in range(1000):
        logfire.warn('warn')
    assert span_counts == snapshot({'start': 720, 'end': 617})
    assert len(exporter.exported_spans) == snapshot(103)
    assert span_counts['end'] + len(exporter.exported_spans) == span_counts['start']

    exporter.clear()
    for _ in range(1000):
        with logfire.span('span'):
            pass
    assert len(exporter.exported_spans_as_dict()) == snapshot(506)

    exporter.clear()
    for _ in range(1000):
        logfire.error('error')
    assert len(exporter.exported_spans) == snapshot(291)
