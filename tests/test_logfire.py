from __future__ import annotations

import inspect
import re
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from logging import getLogger
from typing import Callable

import pytest
from dirty_equals import IsJson, IsStr
from inline_snapshot import snapshot
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from pydantic import BaseModel
from pydantic_core import ValidationError

import logfire
from logfire import Logfire
from logfire._internal.config import LogfireConfig, configure
from logfire._internal.constants import (
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    ATTRIBUTES_TAGS_KEY,
    LEVEL_NUMBERS,
    NULL_ARGS_KEY,
)
from logfire.integrations.logging import LogfireLoggingHandler
from logfire.testing import IncrementalIdGenerator, TestExporter, TimeGenerator


@pytest.mark.parametrize('method', ['trace', 'info', 'debug', 'warn', 'error', 'fatal'])
def test_log_methods_without_kwargs(method: str):
    with pytest.warns(UserWarning, match="The field 'foo' is not defined.") as warnings:
        getattr(logfire, method)('{foo}', bar=2)

    warning = warnings.pop()
    assert warning.filename.endswith('test_logfire.py')


def test_instrument_with_no_args(exporter: TestExporter) -> None:
    @logfire.instrument()
    def foo(x: int):
        return x * 2

    assert foo(2) == 4
    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_with_no_args.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_instrument_with_no_args.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_with_no_args.<locals>.foo',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_with_no_args.<locals>.foo',
                    'x': 2,
                    'logfire.json_schema': '{"type":"object","properties":{"x":{}}}',
                },
            }
        ]
    )


def test_instrument_without_kwargs():
    with pytest.warns(UserWarning, match="The field 'foo' is not defined.") as warnings:

        @logfire.instrument('{foo}')
        def home() -> None: ...

        home()

    warning = warnings.pop()
    assert warning.filename.endswith('test_logfire.py'), (warning.filename, warning.lineno)


def test_span_without_kwargs() -> None:
    with pytest.warns(UserWarning, match="The field 'foo' is not defined.") as warnings:
        with logfire.span('test {foo}'):
            pass  # pragma: no cover

    warning = warnings.pop()
    assert warning.filename.endswith('test_logfire.py')


def test_span_with_kwargs(exporter: TestExporter) -> None:
    with logfire.span('test {name=} {number}', _span_name='test span', name='foo', number=3, extra='extra') as s:
        pass

    assert s.name == 'test span'
    assert s.parent is None
    assert s.start_time is not None
    assert s.end_time is not None
    assert s.start_time < s.end_time
    assert len(s.events) == 0

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test span (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_with_kwargs',
                    'name': 'foo',
                    'number': 3,
                    'extra': 'extra',
                    'logfire.msg_template': 'test {name=} {number}',
                    'logfire.msg': 'test name=foo 3',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{},"extra":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_with_kwargs',
                    'name': 'foo',
                    'number': 3,
                    'extra': 'extra',
                    'logfire.msg_template': 'test {name=} {number}',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{},"extra":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test name=foo 3',
                },
            },
        ]
    )


def test_span_with_parent(exporter: TestExporter) -> None:
    with logfire.span('{type} span', _span_name='test parent span', type='parent') as p:
        with logfire.span('{type} span', _span_name='test child span', type='child') as c:
            pass

    assert p.name == 'test parent span'
    assert p.parent is None
    assert len(p.events) == 0
    assert p.attributes is not None
    assert ATTRIBUTES_TAGS_KEY not in p.attributes

    assert c.name == 'test child span'
    assert c.parent == p.context
    assert len(c.events) == 0
    assert c.attributes is not None
    assert ATTRIBUTES_TAGS_KEY not in c.attributes

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test parent span (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_with_parent',
                    'type': 'parent',
                    'logfire.msg_template': '{type} span',
                    'logfire.msg': 'parent span',
                    'logfire.json_schema': '{"type":"object","properties":{"type":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'test child span (pending)',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_with_parent',
                    'type': 'child',
                    'logfire.msg_template': '{type} span',
                    'logfire.msg': 'child span',
                    'logfire.json_schema': '{"type":"object","properties":{"type":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
            {
                'name': 'test child span',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_with_parent',
                    'type': 'child',
                    'logfire.msg_template': '{type} span',
                    'logfire.json_schema': '{"type":"object","properties":{"type":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'child span',
                },
            },
            {
                'name': 'test parent span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_with_parent',
                    'type': 'parent',
                    'logfire.msg_template': '{type} span',
                    'logfire.json_schema': '{"type":"object","properties":{"type":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'parent span',
                },
            },
        ]
    )


def test_span_with_tags(exporter: TestExporter) -> None:
    with logfire.with_tags('tag1', 'tag2').span(
        'test {name} {number}', _span_name='test span', name='foo', number=3, extra='extra'
    ) as s:
        pass

    assert s.name == 'test span'
    assert s.parent is None
    assert s.start_time is not None and s.end_time is not None
    assert s.start_time < s.end_time
    assert s.attributes is not None
    assert s.attributes[ATTRIBUTES_TAGS_KEY] == ('tag1', 'tag2')
    assert len(s.events) == 0

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test span (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_with_tags',
                    'name': 'foo',
                    'number': 3,
                    'extra': 'extra',
                    'logfire.msg_template': 'test {name} {number}',
                    'logfire.msg': 'test foo 3',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{},"extra":{}}}',
                    'logfire.tags': ('tag1', 'tag2'),
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_with_tags',
                    'name': 'foo',
                    'number': 3,
                    'extra': 'extra',
                    'logfire.msg_template': 'test {name} {number}',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{},"extra":{}}}',
                    'logfire.tags': ('tag1', 'tag2'),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test foo 3',
                },
            },
        ]
    )


def test_span_without_span_name(exporter: TestExporter) -> None:
    with logfire.span('test {name=} {number}', name='foo', number=3, extra='extra') as s:
        pass

    assert s.name == 'test {name=} {number}'
    assert s.parent is None
    assert s.start_time is not None and s.end_time is not None
    assert s.start_time < s.end_time
    assert len(s.events) == 0
    assert s.attributes is not None
    assert ATTRIBUTES_TAGS_KEY not in s.attributes
    assert s.attributes[ATTRIBUTES_MESSAGE_KEY] == 'test name=foo 3'
    assert s.attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] == 'test {name=} {number}'

    assert len(exporter.exported_spans) == 2
    # # because both spans have been ended

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test {name=} {number} (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_without_span_name',
                    'name': 'foo',
                    'number': 3,
                    'extra': 'extra',
                    'logfire.msg_template': 'test {name=} {number}',
                    'logfire.msg': 'test name=foo 3',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{},"extra":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'test {name=} {number}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_without_span_name',
                    'name': 'foo',
                    'number': 3,
                    'extra': 'extra',
                    'logfire.msg_template': 'test {name=} {number}',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{},"extra":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test name=foo 3',
                },
            },
        ]
    )


def test_span_end_on_exit_false(exporter: TestExporter) -> None:
    with logfire.span('test {name=} {number}', name='foo', number=3, extra='extra') as s:
        s.end_on_exit = False

    assert s.name == 'test {name=} {number}'
    assert s.parent is None
    assert s.end_time is None
    assert isinstance(s.start_time, int)
    assert s.attributes is not None
    assert s.attributes[ATTRIBUTES_MESSAGE_KEY] == 'test name=foo 3'
    assert s.attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] == 'test {name=} {number}'

    assert len(exporter.exported_spans) == 1
    span = exporter.exported_spans[0]
    assert span.attributes is not None
    assert span.attributes[ATTRIBUTES_SPAN_TYPE_KEY] == 'pending_span'
    # because the real span hasn't ended yet

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test {name=} {number} (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_end_on_exit_false',
                    'name': 'foo',
                    'number': 3,
                    'extra': 'extra',
                    'logfire.msg_template': 'test {name=} {number}',
                    'logfire.msg': 'test name=foo 3',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{},"extra":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            }
        ]
    )

    with s:
        pass

    assert isinstance(s.end_time, int)
    assert s.end_time > s.start_time
    assert len(exporter.exported_spans) == 2
    span = exporter.exported_spans[1]
    assert span.attributes is not None
    assert span.attributes[ATTRIBUTES_SPAN_TYPE_KEY] == 'span'

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test {name=} {number} (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_end_on_exit_false',
                    'name': 'foo',
                    'number': 3,
                    'extra': 'extra',
                    'logfire.msg_template': 'test {name=} {number}',
                    'logfire.msg': 'test name=foo 3',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{},"extra":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'test {name=} {number}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_end_on_exit_false',
                    'name': 'foo',
                    'number': 3,
                    'extra': 'extra',
                    'logfire.msg_template': 'test {name=} {number}',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{},"extra":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test name=foo 3',
                },
            },
        ]
    )


@pytest.mark.parametrize('level', ('fatal', 'debug', 'error', 'info', 'notice', 'warn', 'trace'))
def test_log(exporter: TestExporter, level: str):
    getattr(logfire, level)('test {name} {number} {none}', name='foo', number=2, none=None)

    s = exporter.exported_spans[0]

    assert s.attributes is not None
    assert s.attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] == 'test {name} {number} {none}'
    assert s.attributes[ATTRIBUTES_MESSAGE_KEY] == 'test foo 2 null'
    assert s.attributes[ATTRIBUTES_SPAN_TYPE_KEY] == 'log'
    assert s.attributes['name'] == 'foo'
    assert s.attributes['number'] == 2
    assert s.attributes[NULL_ARGS_KEY] == ('none',)
    assert ATTRIBUTES_TAGS_KEY not in s.attributes

    # insert_assert(exporter.exported_spans_as_dict(_include_pending_spans=True))
    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == [
        {
            'name': 'test {name} {number} {none}',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_num': LEVEL_NUMBERS[level],
                'logfire.msg_template': 'test {name} {number} {none}',
                'logfire.msg': 'test foo 2 null',
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_log',
                'name': 'foo',
                'number': 2,
                'logfire.null_args': ('none',),
                'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{},"none":{}}}',
            },
        }
    ]


def test_log_equals(exporter: TestExporter) -> None:
    logfire.info('test message {foo=} {bar=}', foo='foo', bar=3)

    s = exporter.exported_spans[0]

    assert s.attributes is not None
    assert s.attributes['logfire.msg'] == 'test message foo=foo bar=3'
    assert s.attributes['foo'] == 'foo'
    assert s.attributes['bar'] == 3
    assert s.attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] == 'test message {foo=} {bar=}'
    assert s.attributes[ATTRIBUTES_SPAN_TYPE_KEY] == 'log'

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test message {foo=} {bar=}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test message {foo=} {bar=}',
                    'logfire.msg': 'test message foo=foo bar=3',
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_log_equals',
                    'foo': 'foo',
                    'bar': 3,
                    'logfire.json_schema': '{"type":"object","properties":{"foo":{},"bar":{}}}',
                },
            }
        ]
    )


def test_log_with_tags(exporter: TestExporter):
    logfire.with_tags('tag1', 'tag2').info('test {name} {number}', name='foo', number=2)

    s = exporter.exported_spans[0]

    assert s.attributes is not None
    assert s.attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] == 'test {name} {number}'
    assert s.attributes[ATTRIBUTES_SPAN_TYPE_KEY] == 'log'
    assert s.attributes['name'] == 'foo'
    assert s.attributes['number'] == 2
    assert s.attributes[ATTRIBUTES_TAGS_KEY] == ('tag1', 'tag2')

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test {name} {number}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test {name} {number}',
                    'logfire.msg': 'test foo 2',
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_log_with_tags',
                    'name': 'foo',
                    'number': 2,
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{}}}',
                    'logfire.tags': ('tag1', 'tag2'),
                },
            }
        ]
    )


def test_log_with_multiple_tags(exporter: TestExporter):
    logfire_with_2_tags = logfire.with_tags('tag1').with_tags('tag2')
    logfire_with_2_tags.info('test {name} {number}', name='foo', number=2)
    assert len(exporter.exported_spans) == 1
    s = exporter.exported_spans[0]
    assert s.attributes is not None
    assert s.attributes[ATTRIBUTES_TAGS_KEY] == ('tag1', 'tag2')

    logfire_with_4_tags = logfire_with_2_tags.with_tags('tag3', 'tag4')
    logfire_with_4_tags.info('test {name} {number}', name='foo', number=2)
    assert len(exporter.exported_spans) == 2
    s = exporter.exported_spans[1]
    assert s.attributes is not None
    assert s.attributes[ATTRIBUTES_TAGS_KEY] == ('tag1', 'tag2', 'tag3', 'tag4')


def test_instrument(exporter: TestExporter):
    @logfire.instrument('hello-world {a=}')
    def hello_world(a: int) -> str:
        return f'hello {a}'

    assert hello_world(123) == 'hello 123'

    assert exporter.exported_spans_as_dict(_include_pending_spans=True, _strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'hello-world {a=} (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_instrument.<locals>.hello_world',
                    'a': 123,
                    'logfire.msg_template': 'hello-world {a=}',
                    'logfire.msg': 'hello-world a=123',
                    'logfire.json_schema': '{"type":"object","properties":{"a":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'hello-world {a=}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_instrument.<locals>.hello_world',
                    'a': 123,
                    'logfire.msg_template': 'hello-world {a=}',
                    'logfire.json_schema': '{"type":"object","properties":{"a":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'hello-world a=123',
                },
            },
        ]
    )


def test_instrument_extract_false(exporter: TestExporter):
    @logfire.instrument('hello {a}!', extract_args=False)
    def hello_world(a: int) -> str:
        return f'hello {a}'

    assert hello_world(123) == 'hello 123'

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'hello {a}!',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_instrument_extract_false.<locals>.hello_world',
                    'logfire.msg_template': 'hello {a}!',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'hello {a}!',
                },
            }
        ]
    )


def test_instrument_complex_args(exporter: TestExporter):
    @logfire.instrument('hello {thing}!')
    def hello_world(thing: dict[str, int]) -> str:
        return f'hello {thing}'

    assert hello_world({'a': 123}) == "hello {'a': 123}"

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'hello {thing}!',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_instrument_complex_args.<locals>.hello_world',
                    'logfire.msg_template': 'hello {thing}!',
                    'logfire.msg': "hello {'a': 123}!",
                    'logfire.json_schema': '{"type":"object","properties":{"thing":{"type":"object"}}}',
                    'thing': '{"a":123}',
                    'logfire.span_type': 'span',
                },
            }
        ]
    )


def test_validation_error_on_instrument(exporter: TestExporter):
    class Model(BaseModel, plugin_settings={'logfire': {'record': 'off'}}):
        a: int

    @logfire.instrument('hello-world {a=}')
    def run(a: str) -> Model:
        return Model(a=a)  # type: ignore

    with pytest.raises(ValidationError):
        run('haha')

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'hello-world {a=}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_validation_error_on_instrument.<locals>.run',
                    'logfire.msg_template': 'hello-world {a=}',
                    'logfire.msg': 'hello-world a=haha',
                    'logfire.json_schema': '{"type":"object","properties":{"a":{}}}',
                    'a': 'haha',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'exception.logfire.data': IsJson(
                        [
                            {
                                'type': 'int_parsing',
                                'loc': ['a'],
                                'msg': 'Input should be a valid integer, unable to parse string as an integer',
                                'input': 'haha',
                            }
                        ]
                    ),
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'ValidationError',
                            'exception.message': IsStr(
                                regex='1 validation error for Model\na\n  '
                                'Input should be a valid integer, unable to parse string as an integer .+',
                                regex_flags=re.DOTALL,
                            ),
                            'exception.stacktrace': IsStr(
                                regex='For further information visit https://errors.pydantic.dev/.+'
                            ),
                            'exception.escaped': 'True',
                            'exception.logfire.data': IsJson(
                                [
                                    {
                                        'type': 'int_parsing',
                                        'loc': ['a'],
                                        'msg': 'Input should be a valid integer, unable to parse string as an integer',
                                        'input': 'haha',
                                    }
                                ]
                            ),
                        },
                    }
                ],
            }
        ]
    )


def test_validation_error_on_span(exporter: TestExporter) -> None:
    class Model(BaseModel, plugin_settings={'logfire': {'record': 'off'}}):
        a: int

    def run(a: str) -> None:
        with logfire.span('test', _span_name='test span'):
            Model(a=a)  # type: ignore

    with pytest.raises(ValidationError):
        run('haha')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'test span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'run',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test',
                    'logfire.msg': 'test',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'exception.logfire.data': IsJson(
                        [
                            {
                                'type': 'int_parsing',
                                'loc': ['a'],
                                'msg': 'Input should be a valid integer, unable to parse string as an integer',
                                'input': 'haha',
                            }
                        ]
                    ),
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'ValidationError',
                            'exception.message': IsStr(
                                regex='1 validation error for Model\na\n  '
                                'Input should be a valid integer, unable to parse string as an integer .+',
                                regex_flags=re.DOTALL,
                            ),
                            'exception.stacktrace': IsStr(
                                regex='For further information visit https://errors.pydantic.dev/.+'
                            ),
                            'exception.escaped': 'True',
                            'exception.logfire.data': IsJson(
                                [
                                    {
                                        'type': 'int_parsing',
                                        'loc': ['a'],
                                        'msg': 'Input should be a valid integer, unable to parse string as an integer',
                                        'input': 'haha',
                                    }
                                ]
                            ),
                        },
                    }
                ],
            }
        ]
    )


@dataclass
class Foo:
    x: int
    y: int


def test_json_args(exporter: TestExporter) -> None:
    logfire.info('test message {foo=}', foo=Foo(1, 2))
    logfire.info('test message {foos=}', foos=[Foo(1, 2)])

    assert len(exporter.exported_spans) == 2
    s = exporter.exported_spans[0]
    assert s.attributes
    assert s.attributes['logfire.msg'] == 'test message foo=Foo(x=1, y=2)'
    assert s.attributes['foo'] == '{"x":1,"y":2}'

    s = exporter.exported_spans[1]
    assert s.attributes
    assert s.attributes['logfire.msg'] == 'test message foos=[Foo(x=1, y=2)]'
    assert s.attributes['foos'] == '[{"x":1,"y":2}]'


def test_int_span_id_encoding():
    """https://github.com/pydantic/platform/pull/388"""

    AnyValue(int_value=2**63 - 1)
    with pytest.raises(ValueError, match='Value out of range: 9223372036854775808'):
        AnyValue(int_value=2**63)
    AnyValue(string_value=str(2**63 - 1))
    AnyValue(string_value=str(2**63))
    AnyValue(string_value=str(2**128))


def test_logfire_with_its_own_config(exporter: TestExporter) -> None:
    exporter1 = TestExporter()
    config = LogfireConfig(
        send_to_logfire=False,
        console=False,
        ns_timestamp_generator=TimeGenerator(),
        id_generator=IncrementalIdGenerator(),
        processors=[
            SimpleSpanProcessor(exporter1),
        ],
    )

    logfire = Logfire(config=config)
    logfire1 = logfire.with_tags('tag1', 'tag2')

    with logfire.span('root'):
        with logfire.span('child'):
            logfire.info('test1')
            logfire1.info('test2')

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot([])

    assert exporter1.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'root (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_logfire_with_its_own_config',
                    'logfire.msg_template': 'root',
                    'logfire.msg': 'root',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'child (pending)',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_logfire_with_its_own_config',
                    'logfire.msg_template': 'child',
                    'logfire.msg': 'child',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_logfire_with_its_own_config',
                },
            },
            {
                'name': 'test2',
                'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test2',
                    'logfire.msg': 'test2',
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_logfire_with_its_own_config',
                    'logfire.tags': ('tag1', 'tag2'),
                },
            },
            {
                'name': 'child',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_logfire_with_its_own_config',
                    'logfire.msg_template': 'child',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'child',
                },
            },
            {
                'name': 'root',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_logfire_with_its_own_config',
                    'logfire.msg_template': 'root',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'root',
                },
            },
        ]
    )


def do_work() -> None:
    with logfire.span('child'):
        pass


def do_work_with_arg(within: str) -> None:
    with logfire.span('child {within}', within=within):
        pass


def test_span_in_executor(
    exporter: TestExporter,
) -> None:
    with logfire.span('main'):
        with ThreadPoolExecutor() as executor:
            executor.submit(do_work)
            executor.shutdown(wait=True)

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'main (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_in_executor',
                    'logfire.msg_template': 'main',
                    'logfire.msg': 'main',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'child (pending)',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'do_work',
                    'logfire.msg_template': 'child',
                    'logfire.msg': 'child',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
            {
                'name': 'child',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'do_work',
                    'logfire.msg_template': 'child',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'child',
                },
            },
            {
                'name': 'main',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_span_in_executor',
                    'logfire.msg_template': 'main',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'main',
                },
            },
        ]
    )


def test_span_in_executor_args(exporter: TestExporter) -> None:
    with ThreadPoolExecutor() as exec:
        exec.submit(do_work_with_arg, 'foo')
        exec.shutdown(wait=True)

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'child {within} (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'do_work_with_arg',
                    'within': 'foo',
                    'logfire.msg_template': 'child {within}',
                    'logfire.msg': 'child foo',
                    'logfire.json_schema': '{"type":"object","properties":{"within":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'child {within}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'do_work_with_arg',
                    'within': 'foo',
                    'logfire.msg_template': 'child {within}',
                    'logfire.json_schema': '{"type":"object","properties":{"within":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'child foo',
                },
            },
        ]
    )


def test_complex_attribute_added_after_span_started(exporter: TestExporter) -> None:
    with logfire.span('hi', a={'b': 1}) as span:
        span.set_attribute('c', {'d': 2})
        span.set_attribute('e', None)
        span.set_attribute('f', None)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_complex_attribute_added_after_span_started',
                    'code.lineno': 123,
                    'a': '{"b":1}',
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'logfire.span_type': 'span',
                    'c': '{"d":2}',
                    'logfire.null_args': ('e', 'f'),
                    'logfire.json_schema': '{"type":"object","properties":{"a":{"type":"object"},"c":{"type":"object"},"e":{},"f":{}}}',
                },
            }
        ]
    )


def test_format_attribute_added_after_pending_span_sent(exporter: TestExporter) -> None:
    with pytest.warns(UserWarning, match=r'missing') as warnings:
        span = logfire.span('{present} {missing}', present='here')

    assert len(warnings) == 1
    assert warnings[0].filename == __file__
    assert warnings[0].lineno == inspect.currentframe().f_lineno - 4  # type: ignore

    with span:
        # Previously the message was reformatted with this attribute, not any more
        span.set_attribute('missing', 'value')

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': '{present} {missing} (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_format_attribute_added_after_pending_span_sent',
                    'present': 'here',
                    'logfire.msg_template': '{present} {missing}',
                    'logfire.msg': 'here {missing}',
                    'logfire.json_schema': '{"type":"object","properties":{"present":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': '{present} {missing}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_format_attribute_added_after_pending_span_sent',
                    'present': 'here',
                    'logfire.msg_template': '{present} {missing}',
                    'logfire.msg': 'here {missing}',
                    'logfire.json_schema': '{"type":"object","properties":{"present":{},"missing":{}}}',
                    'logfire.span_type': 'span',
                    'missing': 'value',
                },
            },
        ]
    )


def check_project_name(expected_project_name: str) -> None:
    from logfire._internal.config import GLOBAL_CONFIG

    assert GLOBAL_CONFIG.project_name == expected_project_name


@pytest.mark.parametrize(
    'executor_factory',
    [
        ThreadPoolExecutor,
        ProcessPoolExecutor,
    ],
)
def test_config_preserved_across_thread_or_process(
    executor_factory: Callable[[], ThreadPoolExecutor | ProcessPoolExecutor],
) -> None:
    """Check that we copy the current global configuration when moving execution to a thread or process."""
    configure(
        send_to_logfire=False,
        console=False,
        project_name='foobar!',
        metric_readers=[InMemoryMetricReader()],
    )

    with executor_factory() as executor:
        executor.submit(check_project_name, 'foobar!')
        executor.shutdown(wait=True)


def test_kwarg_with_dot_in_name(exporter: TestExporter) -> None:
    logfire.info('{http.status}', **{'http.status': 123})  # type: ignore

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': '{http.status}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': '{http.status}',
                    'logfire.msg': '123',
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_kwarg_with_dot_in_name',
                    'http.status': 123,
                    'logfire.json_schema': '{"type":"object","properties":{"http.status":{}}}',
                },
            }
        ]
    )

    exporter.exported_spans.clear()

    with logfire.span('{http.status} - {code.lineno}', **{'http.status': 123}):  # type: ignore
        pass

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': '{http.status} - {code.lineno} (pending)',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_kwarg_with_dot_in_name',
                    'http.status': 123,
                    'logfire.msg_template': '{http.status} - {code.lineno}',
                    'logfire.msg': IsStr(regex=r'123 - \d+'),
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                    'logfire.json_schema': '{"type":"object","properties":{"http.status":{}}}',
                },
            },
            {
                'name': '{http.status} - {code.lineno}',
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_kwarg_with_dot_in_name',
                    'http.status': 123,
                    'logfire.msg_template': '{http.status} - {code.lineno}',
                    'logfire.msg': IsStr(regex=r'123 - \d+'),
                    'logfire.span_type': 'span',
                    'logfire.json_schema': '{"type":"object","properties":{"http.status":{}}}',
                },
            },
        ]
    )


@pytest.mark.parametrize('method', ('trace', 'debug', 'info', 'notice', 'warn', 'error', 'fatal', 'span'))
def test_forbid_methods_with_leading_underscore_on_attributes(method: str) -> None:
    with pytest.raises(ValueError, match='Attribute keys cannot start with an underscore.'):
        getattr(logfire, method)('test {_foo=}', _foo='bar')

    with pytest.raises(ValueError, match='Attribute keys cannot start with an underscore.'):
        getattr(logfire, method)('test {__foo=}', __foo='bar')


def test_log_with_leading_underscore_on_attributes(exporter: TestExporter) -> None:
    logfire.log('info', 'test {_foo=}', attributes={'_foo': 'bar'})

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test {_foo=}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test {_foo=}',
                    'logfire.msg': 'test _foo=bar',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_log_with_leading_underscore_on_attributes',
                    'code.lineno': 123,
                    '_foo': 'bar',
                    'logfire.json_schema': '{"type":"object","properties":{"_foo":{}}}',
                },
            }
        ]
    )


def test_large_int(exporter: TestExporter) -> None:
    with pytest.warns(UserWarning, match='larger than the maximum OTLP integer size'):
        with logfire.span('test {value=}', value=2**63 + 1):
            pass

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test {value=} (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_large_int',
                    'value': '9223372036854775809',
                    'logfire.msg_template': 'test {value=}',
                    'logfire.msg': 'test value=9223372036854775809',
                    'logfire.json_schema': '{"type":"object","properties":{"value":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'test {value=}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_large_int',
                    'value': '9223372036854775809',
                    'logfire.msg_template': 'test {value=}',
                    'logfire.json_schema': '{"type":"object","properties":{"value":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test value=9223372036854775809',
                },
            },
        ]
    )
    exporter.exported_spans.clear()

    with pytest.warns(UserWarning, match='larger than the maximum OTLP integer size'):
        with logfire.span('test {value=}', value=2**63):
            pass

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test {value=} (pending)',
                'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_large_int',
                    'value': '9223372036854775808',
                    'logfire.msg_template': 'test {value=}',
                    'logfire.msg': 'test value=9223372036854775808',
                    'logfire.json_schema': '{"type":"object","properties":{"value":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'test {value=}',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_large_int',
                    'value': '9223372036854775808',
                    'logfire.msg_template': 'test {value=}',
                    'logfire.json_schema': '{"type":"object","properties":{"value":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test value=9223372036854775808',
                },
            },
        ]
    )
    exporter.exported_spans.clear()

    with logfire.span('test {value=}', value=2**63 - 1):
        pass

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test {value=} (pending)',
                'context': {'trace_id': 3, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_large_int',
                    'value': 9223372036854775807,
                    'logfire.msg_template': 'test {value=}',
                    'logfire.msg': 'test value=9223372036854775807',
                    'logfire.json_schema': '{"type":"object","properties":{"value":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'test {value=}',
                'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_large_int',
                    'value': 9223372036854775807,
                    'logfire.msg_template': 'test {value=}',
                    'logfire.json_schema': '{"type":"object","properties":{"value":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test value=9223372036854775807',
                },
            },
        ]
    )


def test_readable_span_signature():
    # This is to test that we are providing all the arguments we can when
    # constructing ReadableSpans (e.g. in PendingSpanProcessor and SpanProcessorWrapper)
    # i.e. if this test fails it means that the OTEL SDK has been updated
    # and places in our code constructing ReadableSpans needs to be updated to add the new arguments.
    signature = inspect.signature(ReadableSpan.__init__)
    assert set(signature.parameters.keys()) == {
        'self',
        'name',
        'context',
        'parent',
        'resource',
        'attributes',
        'events',
        'links',
        'status',
        'kind',
        'start_time',
        'end_time',
        'instrumentation_scope',
        # Apart from `self`, this is the only argument that we currently don't use,
        # because the property is deprecated.
        # Hopefully that means that it's not important or used much.
        # Either way it's probably not a disaster if it isn't in the pending span,
        # it'll still make it in the final span.
        'instrumentation_info',
    }


def test_tags(exporter: TestExporter) -> None:
    lf = logfire.with_tags('tag1', 'tag2')
    with lf.span('a span', _tags=('tag2', 'tag3')):
        lf.info('a log', _tags=('tag4', 'tag1'))

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'a log',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'a log',
                    'logfire.msg': 'a log',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_tags',
                    'code.lineno': 123,
                    'logfire.tags': ('tag1', 'tag2', 'tag4'),
                },
            },
            {
                'name': 'a span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_tags',
                    'code.lineno': 123,
                    'logfire.msg_template': 'a span',
                    'logfire.msg': 'a span',
                    'logfire.tags': ('tag1', 'tag2', 'tag3'),
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_exc_info(exporter: TestExporter):
    logger = getLogger(__name__)
    logger.addHandler(LogfireLoggingHandler())

    logfire.debug('no error', _exc_info=True)
    logger.error('no error', exc_info=True)

    try:
        raise TypeError('other error')
    except TypeError as e:
        other_error = e
        other_exc_info = sys.exc_info()

    try:
        raise ValueError('an error')
    except ValueError as e:
        logfire.trace('exc0', _exc_info=other_error)
        logfire.notice('exc1', _exc_info=other_exc_info)
        logfire.info('exc2', _exc_info=e)
        logfire.warn('exc3', _exc_info=True)
        logfire.error('exc4', _exc_info=sys.exc_info())
        logfire.exception('exc5')
        logger.exception('exc6')

    span_dicts = exporter.exported_spans_as_dict()

    assert len(span_dicts) == 9

    for span_dict in span_dicts[:2]:
        assert 'events' not in span_dict

    for span_dict in span_dicts[2:4]:
        [event] = span_dict['events']
        assert event['attributes'] == {
            'exception.type': 'TypeError',
            'exception.message': 'other error',
            'exception.stacktrace': 'TypeError: other error',
            'exception.escaped': 'False',
        }

    for span_dict in span_dicts[4:]:
        [event] = span_dict['events']
        assert event['attributes'] == {
            'exception.type': 'ValueError',
            'exception.message': 'an error',
            'exception.stacktrace': 'ValueError: an error',
            'exception.escaped': 'False',
        }


def test_span_level(exporter: TestExporter):
    with logfire.span('foo', _level='debug') as span:
        span.set_level('warn')

    # debug when pending, warn when finished
    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'foo (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_span_level',
                    'code.lineno': 123,
                    'logfire.msg_template': 'foo',
                    'logfire.msg': 'foo',
                    'logfire.level_num': 5,
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_span_level',
                    'code.lineno': 123,
                    'logfire.msg_template': 'foo',
                    'logfire.msg': 'foo',
                    'logfire.level_num': 13,
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_span_set_level_before_start(exporter: TestExporter):
    span = logfire.span('foo', _level='debug')
    span.set_level('warn')
    with span:
        pass

    # warn from the beginning
    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'foo (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_span_set_level_before_start',
                    'code.lineno': 123,
                    'logfire.msg_template': 'foo',
                    'logfire.msg': 'foo',
                    'logfire.level_num': 13,
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_span_set_level_before_start',
                    'code.lineno': 123,
                    'logfire.msg_template': 'foo',
                    'logfire.msg': 'foo',
                    'logfire.level_num': 13,
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_invalid_log_level(exporter: TestExporter):
    with pytest.warns(UserWarning, match="Invalid log level name: 'bad_log_level'"):
        logfire.log('bad_log_level', 'log message')  # type: ignore

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'log message',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'log message',
                    'logfire.msg': 'log message',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_invalid_log_level',
                    'code.lineno': 123,
                },
            }
        ]
    )
