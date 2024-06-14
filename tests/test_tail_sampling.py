from typing import Any

from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter


def test_level_sampling(config_kwargs: dict[str, Any], exporter: TestExporter):
    logfire.configure(**config_kwargs, tail_sampling=logfire.TailSamplingOptions(duration=None))

    with logfire.span('ignored span'):
        logfire.debug('debug')
    logfire.notice('notice')
    with logfire.span('ignored span'):
        logfire.info('info')
    logfire.warn('warn')

    with logfire.span('span'):
        with logfire.span('span2'):
            logfire.error('error')

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


def test_duration_sampling(config_kwargs: dict[str, Any], exporter: TestExporter):
    logfire.configure(**config_kwargs, tail_sampling=logfire.TailSamplingOptions(level=None, duration=3))

    logfire.info('short1')
    with logfire.span('span'):
        logfire.info('short2')
    with logfire.span('span2'):
        with logfire.span('span3'):
            pass
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
