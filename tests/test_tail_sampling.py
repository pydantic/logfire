from __future__ import annotations

from typing import Any

import inline_snapshot.extra
import pytest
from inline_snapshot import snapshot
from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON, Sampler, SamplingResult

import logfire
from logfire._internal.constants import LEVEL_NUMBERS
from logfire.sampling import SpanLevel, TailSamplingSpanInfo
from logfire.testing import SeededRandomIdGenerator, TestExporter, TimeGenerator


def test_level_threshold(config_kwargs: dict[str, Any], exporter: TestExporter):
    # Use the default TailSamplingOptions.level of 'notice'.
    # Set duration to None to not include spans with a long duration.
    logfire.configure(**config_kwargs, sampling=logfire.SamplingOptions.level_or_duration(duration_threshold=None))

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
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 10,
                    'logfire.msg_template': 'notice',
                    'logfire.msg': 'notice',
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_threshold',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'warn',
                'context': {'trace_id': 4, 'span_id': 6, 'is_remote': False},
                'parent': None,
                'start_time': 8000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'warn',
                    'logfire.msg': 'warn',
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_threshold',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'span',
                'context': {'trace_id': 5, 'span_id': 10, 'is_remote': False},
                'parent': {'trace_id': 5, 'span_id': 7, 'is_remote': False},
                'start_time': 9000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_threshold',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'span2',
                'context': {'trace_id': 5, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 5, 'span_id': 8, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_threshold',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span2',
                    'logfire.msg': 'span2',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000007',
                },
            },
            {
                'name': 'error',
                'context': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 5, 'span_id': 8, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 11000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'error',
                    'logfire.msg': 'error',
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_threshold',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'span2',
                'context': {'trace_id': 5, 'span_id': 8, 'is_remote': False},
                'parent': {'trace_id': 5, 'span_id': 7, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 12000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_threshold',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span2',
                    'logfire.msg': 'span2',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'span',
                'context': {'trace_id': 5, 'span_id': 7, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 13000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_threshold',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'span3',
                'context': {'trace_id': 6, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 6, 'span_id': 12, 'is_remote': False},
                'start_time': 14000000000,
                'end_time': 14000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_threshold',
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
                'context': {'trace_id': 6, 'span_id': 14, 'is_remote': False},
                'parent': {'trace_id': 6, 'span_id': 12, 'is_remote': False},
                'start_time': 15000000000,
                'end_time': 15000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 1,
                    'logfire.msg_template': 'trace',
                    'logfire.msg': 'trace',
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_threshold',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'span3',
                'context': {'trace_id': 6, 'span_id': 12, 'is_remote': False},
                'parent': None,
                'start_time': 14000000000,
                'end_time': 16000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_level_threshold',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span3',
                    'logfire.msg': 'span3',
                    'logfire.level_num': 21,
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_duration_threshold(
    config_kwargs: dict[str, Any],
    exporter: TestExporter,
    time_generator: TimeGenerator,
):
    # Set level to None to not include spans merely based on a high level.
    logfire.configure(
        **config_kwargs, sampling=logfire.SamplingOptions.level_or_duration(level_threshold=None, duration_threshold=3)
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

    # This reaches the duration threshold when span7 ends but before span6 ends.
    # This means that a pending span is created for span6 but not for span7,
    # because PendingSpanProcessor doesn't create pending spans for spans that have finished.
    with logfire.span('span6'):
        time_generator()
        with logfire.span('span7'):
            time_generator()

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'long1',
                'context': {'trace_id': 4, 'span_id': 8, 'is_remote': False},
                'parent': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 11000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'long1',
                    'logfire.msg': 'long1',
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_duration_threshold',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'span5',
                'context': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 4, 'span_id': 6, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 12000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_duration_threshold',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span5',
                    'logfire.msg': 'span5',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'span4',
                'context': {'trace_id': 4, 'span_id': 6, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 13000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_duration_threshold',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span4',
                    'logfire.msg': 'span4',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'span6',
                'context': {'trace_id': 5, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'start_time': 14000000000,
                'end_time': 14000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_duration_threshold',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span6',
                    'logfire.msg': 'span6',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'span7',
                'context': {'trace_id': 5, 'span_id': 10, 'is_remote': False},
                'parent': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'start_time': 16000000000,
                'end_time': 18000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_duration_threshold',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span7',
                    'logfire.msg': 'span7',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'span6',
                'context': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 14000000000,
                'end_time': 19000000000,
                'attributes': {
                    'code.filepath': 'test_tail_sampling.py',
                    'code.function': 'test_duration_threshold',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span6',
                    'logfire.msg': 'span6',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_background_rate(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs.update(
        sampling=logfire.SamplingOptions.level_or_duration(background_rate=0.3),
    )
    config_kwargs['advanced'].id_generator = SeededRandomIdGenerator(seed=1)
    logfire.configure(**config_kwargs)
    # These spans should all be included because the level is above the default.
    for _ in range(100):
        logfire.error('error')
    assert len(exporter.exported_spans) == 100

    # About 30% these spans (i.e. an extra ~300) should be included because of the background_rate.
    # None of them meet the tail sampling criteria.
    for _ in range(1000):
        logfire.info('info')
    assert len(exporter.exported_spans) - 100 == snapshot(299)


class TestSampler(Sampler):
    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        *args: Any,
        **kwargs: Any,
    ) -> SamplingResult:
        if name == 'exclude':
            sampler = ALWAYS_OFF
        else:
            sampler = ALWAYS_ON
        return sampler.should_sample(parent_context, trace_id, name, *args, **kwargs)

    def get_description(self) -> str:  # pragma: no cover
        return 'MySampler'


def test_raw_head_sampler_without_tail_sampling(config_kwargs: dict[str, Any], exporter: TestExporter):
    logfire.configure(
        **config_kwargs,
        sampling=logfire.SamplingOptions(head=TestSampler()),
    )

    # These spans should all be excluded by the head sampler
    for _ in range(100):
        logfire.error('exclude')
    assert len(exporter.exported_spans) == 0

    for _ in range(100):
        logfire.error('error')
    assert len(exporter.exported_spans) == 100


def test_raw_head_sampler_with_tail_sampling(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs.update(
        sampling=logfire.SamplingOptions.level_or_duration(head=TestSampler(), background_rate=0.3),
    )
    config_kwargs['advanced'].id_generator = SeededRandomIdGenerator(seed=1)
    logfire.configure(**config_kwargs)

    # These spans should all be excluded by the head sampler,
    # so it doesn't matter that they have a high level.
    for _ in range(100):
        logfire.error('exclude')
    assert len(exporter.exported_spans) == 0

    # These spans should all be included because the level is above the default,
    # and the head sampler doesn't exclude them.
    for _ in range(100):
        logfire.error('error')
    assert len(exporter.exported_spans) == 100

    # About 30% these spans (i.e. an extra ~300) should be included because of the background_rate.
    # None of them meet the tail sampling criteria.
    for _ in range(1000):
        logfire.info('info')
    assert len(exporter.exported_spans) - 100 == snapshot(293)


def test_custom_head_and_tail(config_kwargs: dict[str, Any], exporter: TestExporter):
    span_counts = {'start': 0, 'end': 0}

    def get_tail_sample_rate(span_info: TailSamplingSpanInfo) -> float:
        span_counts[span_info.event] += 1
        if span_info.duration >= 1:
            return 0.5
        if span_info.level > 'warn':
            return 0.3
        return 0.1

    config_kwargs.update(
        sampling=logfire.SamplingOptions(
            head=0.7,
            tail=get_tail_sample_rate,
        ),
    )
    config_kwargs['advanced'].id_generator = SeededRandomIdGenerator(seed=3)

    logfire.configure(**config_kwargs)

    for _ in range(1000):
        logfire.warn('warn')
    assert span_counts == snapshot({'start': 719, 'end': 611})
    assert len(exporter.exported_spans) == snapshot(108)
    assert span_counts['end'] + len(exporter.exported_spans) == span_counts['start']

    exporter.clear()
    for _ in range(1000):
        with logfire.span('span'):
            pass
    assert len(exporter.exported_spans_as_dict()) == snapshot(511)

    exporter.clear()
    for _ in range(1000):
        logfire.error('error')
    assert len(exporter.exported_spans) == snapshot(298)


def test_span_levels():
    warn = SpanLevel(LEVEL_NUMBERS['warn'])

    assert 'warn' <= warn <= 'warn'
    assert 'debug' <= warn <= 'error'
    assert 'info' < warn < 'fatal'
    assert not (warn < 'warn')
    assert not (warn > 'warn')
    assert not (warn > 'fatal')
    assert not (warn >= 'fatal')
    assert not (warn < 'debug')
    assert not (warn <= 'debug')

    assert warn == 'warn'
    assert warn != 'error'
    assert not (warn != 'warn')
    assert not (warn == 'error')
    assert warn == warn.number
    assert warn != 123
    assert warn == warn
    assert not (warn != warn)
    assert warn != SpanLevel(LEVEL_NUMBERS['error'])
    assert not (warn == SpanLevel(LEVEL_NUMBERS['error']))
    assert warn == SpanLevel(LEVEL_NUMBERS['warn'])
    assert not (warn != SpanLevel(LEVEL_NUMBERS['warn']))

    assert warn.number == LEVEL_NUMBERS['warn'] == 13
    assert warn.name == 'warn'

    assert warn != 'foo'
    assert warn != [1, 2, 3]
    assert not (warn == [1, 2, 3])
    assert not ([1, 2, 3] == warn)

    assert {warn, SpanLevel(LEVEL_NUMBERS['warn'])} == {warn}


def test_invalid_rates():
    with inline_snapshot.extra.raises(
        snapshot('ValueError: Invalid sampling rates, must be 0.0 <= background_rate <= head <= 1.0')
    ):
        logfire.SamplingOptions.level_or_duration(background_rate=-1)
    with pytest.raises(ValueError):
        logfire.SamplingOptions.level_or_duration(background_rate=0.5, head=0.3)
    with pytest.raises(ValueError):
        logfire.SamplingOptions.level_or_duration(head=2)


def test_trace_sample_rate(config_kwargs: dict[str, Any]):
    with pytest.warns(UserWarning) as warnings:
        logfire.configure(trace_sample_rate=0.123, **config_kwargs)  # type: ignore
    assert logfire.DEFAULT_LOGFIRE_INSTANCE.config.sampling.head == 0.123
    assert len(warnings) == 1
    assert str(warnings[0].message) == snapshot(
        'The `trace_sample_rate` argument is deprecated. Use `sampling=logfire.SamplingOptions(head=...)` instead.'
    )


def test_both_trace_and_head():
    with inline_snapshot.extra.raises(
        snapshot(
            'ValueError: Cannot specify both `trace_sample_rate` and `sampling`. '
            'Use `sampling.head` instead of `trace_sample_rate`.'
        )
    ):
        logfire.configure(trace_sample_rate=0.5, sampling=logfire.SamplingOptions())  # type: ignore
