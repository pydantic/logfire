from __future__ import annotations

import json
import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, cast

import pytest
from dirty_equals import IsPositive, IsStr
from opentelemetry.exporter.otlp.proto.common._internal.trace_encoder import encode_spans
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from pydantic import BaseModel
from pydantic_core import ValidationError

import logfire
from logfire import Logfire, LogfireSpan
from logfire._config import ConsoleOptions, LogfireConfig, configure
from logfire._constants import (
    ATTRIBUTES_LOG_LEVEL_KEY,
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    ATTRIBUTES_TAGS_KEY,
    NULL_ARGS_KEY,
)
from logfire.testing import IncrementalIdGenerator, TestExporter, TimeGenerator


@pytest.mark.parametrize('method', ['info', 'debug', 'warning', 'error', 'critical'])
def test_log_methods_without_kwargs(method: str):
    with pytest.warns(UserWarning, match="The field 'foo' is not defined.") as warnings:
        getattr(logfire, method)('{foo}', bar=2)

    warning = warnings.pop()
    assert warning.filename.endswith('test_logfire.py')


def test_instrument_without_kwargs():
    with pytest.warns(UserWarning, match="The field 'foo' is not defined.") as warnings:

        @logfire.instrument('{foo}')
        def home() -> None:
            ...

        home()

    warning = warnings.pop()
    assert warning.filename.endswith('test_logfire.py'), (warning.filename, warning.lineno)


def test_span_without_kwargs(exporter: TestExporter) -> None:
    with pytest.warns(UserWarning, match="The field 'foo' is not defined.") as warnings:
        with logfire.span('test {foo}', span_name='test span'):
            pass  # pragma: no cover

    warning = warnings.pop()
    assert warning.filename.endswith('test_logfire.py')


def test_span_with_kwargs(exporter: TestExporter) -> None:
    with logfire.span('test {name=} {number}', span_name='test span', name='foo', number=3, extra='extra') as s:
        pass

    assert s.name == 'test span'
    assert s.parent is None
    assert s.start_time is not None
    assert s.end_time is not None
    assert s.start_time < s.end_time
    assert len(s.events) == 0

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'test span (start)',
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
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
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
                'logfire.msg': 'test name=foo 3',
                'logfire.span_type': 'span',
            },
        },
    ]


def test_span_with_parent(exporter: TestExporter) -> None:
    with logfire.span('{type} span', span_name='test parent span', type='parent') as p:
        with logfire.span('{type} span', span_name='test child span', type='child') as c:
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

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'test parent span (start)',
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
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'test child span (start)',
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
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '1',
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
                'logfire.msg': 'child span',
                'logfire.span_type': 'span',
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
                'logfire.msg': 'parent span',
                'logfire.span_type': 'span',
            },
        },
    ]


def test_span_with_tags(exporter: TestExporter) -> None:
    with logfire.with_tags('tag1', 'tag2').span(
        'test {name} {number}', span_name='test span', name='foo', number=3, extra='extra'
    ) as s:
        pass

    assert s.name == 'test span'
    assert s.parent is None
    assert s.start_time is not None and s.end_time is not None
    assert s.start_time < s.end_time
    assert s.attributes is not None
    assert s.attributes[ATTRIBUTES_TAGS_KEY] == ('tag1', 'tag2')
    assert len(s.events) == 0

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'test span (start)',
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
                'logfire.tags': ('tag1', 'tag2'),
                'logfire.msg_template': 'test {name} {number}',
                'logfire.msg': 'test foo 3',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
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
                'logfire.tags': ('tag1', 'tag2'),
                'logfire.msg_template': 'test {name} {number}',
                'logfire.msg': 'test foo 3',
                'logfire.span_type': 'span',
            },
        },
    ]


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

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'test {name=} {number} (start)',
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
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
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
                'logfire.msg': 'test name=foo 3',
                'logfire.span_type': 'span',
            },
        },
    ]


def test_span_use_span_name_in_formatting(exporter: TestExporter) -> None:
    with logfire.span('test {name=} {number} {span_name}', span_name='bar', name='foo', number=3, extra='extra') as s:
        pass

    assert isinstance(s, LogfireSpan)
    assert s.name == 'bar'
    assert s.parent is None
    assert s.start_time is not None and s.end_time is not None
    assert s.start_time < s.end_time
    assert len(s.events) == 0
    assert s.attributes is not None
    assert ATTRIBUTES_TAGS_KEY not in s.attributes
    assert s.attributes[ATTRIBUTES_MESSAGE_KEY] == 'test name=foo 3 bar'
    assert s.attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] == 'test {name=} {number} {span_name}'

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'bar (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_span_use_span_name_in_formatting',
                'name': 'foo',
                'number': 3,
                'extra': 'extra',
                'logfire.msg_template': 'test {name=} {number} {span_name}',
                'logfire.msg': 'test name=foo 3 bar',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'bar',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_span_use_span_name_in_formatting',
                'name': 'foo',
                'number': 3,
                'extra': 'extra',
                'logfire.msg_template': 'test {name=} {number} {span_name}',
                'logfire.msg': 'test name=foo 3 bar',
                'logfire.span_type': 'span',
            },
        },
    ]


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
    assert span.attributes[ATTRIBUTES_SPAN_TYPE_KEY] == 'start_span'
    # because the real span hasn't ended yet

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'test {name=} {number} (start)',
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
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        }
    ]

    with s.activate(end_on_exit=True):
        pass

    assert isinstance(s.end_time, int)
    assert s.end_time > s.start_time
    assert len(exporter.exported_spans) == 2
    span = exporter.exported_spans[1]
    assert span.attributes is not None
    assert span.attributes[ATTRIBUTES_SPAN_TYPE_KEY] == 'span'

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'test {name=} {number} (start)',
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
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
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
                'logfire.msg': 'test name=foo 3',
                'logfire.span_type': 'span',
            },
        },
    ]


@pytest.mark.parametrize('level', ('critical', 'debug', 'error', 'info', 'notice', 'warning'))
def test_log(exporter: TestExporter, level: str):
    getattr(logfire, level)('test {name} {number} {none}', name='foo', number=2, none=None)

    s = exporter.exported_spans[0]

    assert s.attributes is not None
    assert s.attributes[ATTRIBUTES_LOG_LEVEL_KEY] == level
    assert s.attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] == 'test {name} {number} {none}'
    assert s.attributes[ATTRIBUTES_MESSAGE_KEY] == 'test foo 2 null'
    assert s.attributes[ATTRIBUTES_SPAN_TYPE_KEY] == 'log'
    assert s.attributes['name'] == 'foo'
    assert s.attributes['number'] == 2
    assert s.attributes[NULL_ARGS_KEY] == ('none',)
    assert ATTRIBUTES_TAGS_KEY not in s.attributes

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'test foo 2 null',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': level,
                'logfire.msg_template': 'test {name} {number} {none}',
                'logfire.msg': 'test foo 2 null',
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_log',
                'name': 'foo',
                'number': 2,
                'logfire.null_args': ('none',),
            },
        }
    ]


def test_log_equals(exporter: TestExporter) -> None:
    logfire.info('test message {foo=} {bar=}', foo='foo', bar=3)

    s = exporter.exported_spans[0]

    assert s.name == 'test message foo=foo bar=3'
    assert s.attributes is not None
    assert s.attributes['foo'] == 'foo'
    assert s.attributes['bar'] == 3
    assert s.attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] == 'test message {foo=} {bar=}'
    assert s.attributes[ATTRIBUTES_LOG_LEVEL_KEY] == 'info'
    assert s.attributes[ATTRIBUTES_SPAN_TYPE_KEY] == 'log'

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'test message foo=foo bar=3',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'info',
                'logfire.msg_template': 'test message {foo=} {bar=}',
                'logfire.msg': 'test message foo=foo bar=3',
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_log_equals',
                'foo': 'foo',
                'bar': 3,
            },
        }
    ]


def test_log_with_tags(exporter: TestExporter):
    logfire.with_tags('tag1', 'tag2').info('test {name} {number}', name='foo', number=2)

    s = exporter.exported_spans[0]

    assert s.attributes is not None
    assert s.attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] == 'test {name} {number}'
    assert s.attributes[ATTRIBUTES_SPAN_TYPE_KEY] == 'log'
    assert s.attributes['name'] == 'foo'
    assert s.attributes['number'] == 2
    assert s.attributes[ATTRIBUTES_TAGS_KEY] == ('tag1', 'tag2')

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'test foo 2',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'info',
                'logfire.msg_template': 'test {name} {number}',
                'logfire.msg': 'test foo 2',
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_log_with_tags',
                'name': 'foo',
                'number': 2,
                'logfire.tags': ('tag1', 'tag2'),
            },
        }
    ]


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

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'tests.test_logfire.test_instrument.<locals>.hello_world (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_instrument',
                'a': 123,
                'logfire.msg_template': 'hello-world {a=}',
                'logfire.msg': 'hello-world a=123',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'tests.test_logfire.test_instrument.<locals>.hello_world',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_instrument',
                'a': 123,
                'logfire.msg_template': 'hello-world {a=}',
                'logfire.span_type': 'span',
                'logfire.msg': 'hello-world a=123',
            },
        },
    ]


def test_instrument_extract_false(exporter: TestExporter):
    @logfire.instrument('hello-world', extract_args=False)
    def hello_world(a: int) -> str:
        return f'hello {a}'

    assert hello_world(123) == 'hello 123'

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'tests.test_logfire.test_instrument_extract_false.<locals>.hello_world (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_instrument_extract_false',
                'logfire.msg_template': 'hello-world',
                'logfire.msg': 'hello-world',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'tests.test_logfire.test_instrument_extract_false.<locals>.hello_world',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_instrument_extract_false',
                'logfire.msg_template': 'hello-world',
                'logfire.span_type': 'span',
                'logfire.msg': 'hello-world',
            },
        },
    ]


def test_validation_error_on_instrument(exporter: TestExporter):
    class Model(BaseModel, plugin_settings={'logfire': {'record': 'off'}}):
        a: int

    @logfire.instrument('hello-world {a=}')
    def run(a: str) -> Model:
        return Model(a=a)  # type: ignore

    with pytest.raises(ValidationError):
        run('haha')

    s = exporter.exported_spans.pop()
    assert len(s.events) == 1
    event = s.events[0]
    assert event.name == 'exception' and event.attributes
    assert event.attributes.get('exception.type') == 'ValidationError'
    assert '1 validation error for Model' in cast(str, event.attributes.get('exception.message'))
    assert event.attributes.get('exception.stacktrace') is not None

    data = json.loads(cast(str, event.attributes.get('exception.logfire.data')))
    # insert_assert(data)
    assert data == [
        {
            'type': 'int_parsing',
            'loc': ['a'],
            'msg': 'Input should be a valid integer, unable to parse string as an integer',
            'input': 'haha',
        }
    ]

    errors = json.loads(cast(str, event.attributes.get('exception.logfire.trace')))
    # insert_assert(errors)
    assert errors == {
        'stacks': [
            {
                'exc_type': 'ValidationError',
                'exc_value': IsStr(
                    regex=(
                        re.escape(
                            "1 validation error for Model\n"
                            "a\n"
                            "  Input should be a valid integer, unable to parse string as an integer "
                            "[type=int_parsing, input_value='haha', input_type=str]\n"
                        )
                        + r'    For further information visit https://errors\.pydantic\.dev/[\d\.]+/v/int_parsing'
                    ),
                    regex_flags=re.MULTILINE,
                ),
                'syntax_error': None,
                'is_cause': False,
                'frames': [
                    {
                        'filename': IsStr(regex=r'.*/tests/test_logfire.py'),
                        'lineno': IsPositive(),
                        'name': 'run',
                        'line': '',
                        'locals': None,
                    },
                    {
                        'filename': IsStr(regex=r'.*/pydantic/main.py'),
                        'lineno': IsPositive(),
                        'name': '__init__',
                        'line': '',
                        'locals': None,
                    },
                ],
            }
        ]
    }


def test_validation_error_on_span(exporter: TestExporter) -> None:
    class Model(BaseModel, plugin_settings={'logfire': {'record': 'off'}}):
        a: int

    def run(a: str) -> None:
        with logfire.span('test', span_name='test span'):
            Model(a=a)  # type: ignore

    with pytest.raises(ValidationError):
        run('haha')

    s = exporter.exported_spans.pop()
    assert len(s.events) == 1
    event = s.events[0]
    assert event.name == 'exception' and event.attributes
    assert event.attributes.get('exception.type') == 'ValidationError'
    assert '1 validation error for Model' in cast(str, event.attributes.get('exception.message'))
    assert event.attributes.get('exception.stacktrace') is not None

    data = json.loads(cast(bytes, event.attributes.get('exception.logfire.data')))
    # insert_assert(data)
    assert data == [
        {
            'type': 'int_parsing',
            'loc': ['a'],
            'msg': 'Input should be a valid integer, unable to parse string as an integer',
            'input': 'haha',
        }
    ]

    errors = json.loads(cast(bytes, event.attributes.get('exception.logfire.trace')))
    # insert_assert(errors)
    assert errors == {
        'stacks': [
            {
                'exc_type': 'ValidationError',
                'exc_value': IsStr(
                    regex=(
                        re.escape(
                            "1 validation error for Model\n"
                            "a\n"
                            "  Input should be a valid integer, unable to parse string as an integer "
                            "[type=int_parsing, input_value='haha', input_type=str]\n"
                        )
                        + r'    For further information visit https://errors\.pydantic\.dev/[\d\.]+/v/int_parsing'
                    ),
                    regex_flags=re.MULTILINE,
                ),
                'syntax_error': None,
                'is_cause': False,
                'frames': [
                    {
                        'filename': IsStr(regex=r'.*/tests/test_logfire.py'),
                        'lineno': IsPositive(),
                        'name': 'run',
                        'line': '',
                        'locals': None,
                    },
                    {
                        'filename': IsStr(regex=r'.*/pydantic/main.py'),
                        'lineno': IsPositive(),
                        'name': '__init__',
                        'line': '',
                        'locals': None,
                    },
                ],
            }
        ]
    }


@dataclass
class Foo:
    x: int
    y: int


def test_json_args(exporter: TestExporter) -> None:
    logfire.info('test message {foo=}', foo=Foo(1, 2))
    logfire.info('test message {foos=}', foos=[Foo(1, 2)])

    assert len(exporter.exported_spans) == 2
    s = exporter.exported_spans[0]
    assert s.name == 'test message foo=Foo(x=1, y=2)'
    assert s.attributes is not None
    assert s.attributes['foo__JSON'] == '{"$__datatype__":"dataclass","data":{"x":1,"y":2},"cls":"Foo"}'

    s = exporter.exported_spans[1]
    assert s.name == 'test message foos=[Foo(x=1, y=2)]'
    assert s.attributes is not None
    assert s.attributes['foos__JSON'] == '[{"$__datatype__":"dataclass","data":{"x":1,"y":2},"cls":"Foo"}]'


def test_int_span_id_encoding():
    """https://github.com/pydantic/platform/pull/388"""

    AnyValue(int_value=2**63 - 1)
    with pytest.raises(ValueError, match='Value out of range: 9223372036854775808'):
        AnyValue(int_value=2**63)
    AnyValue(string_value=str(2**63 - 1))
    AnyValue(string_value=str(2**63))
    AnyValue(string_value=str(2**128))


def test_logifre_with_its_own_config(exporter: TestExporter) -> None:
    exporter1 = TestExporter()
    config = LogfireConfig(
        send_to_logfire=False,
        console=ConsoleOptions(enabled=False),
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

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == []

    # insert_assert(exporter1.exported_spans_as_dict(_include_start_spans=True))
    assert exporter1.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'root (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_logifre_with_its_own_config',
                'logfire.msg_template': 'root',
                'logfire.msg': 'root',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'child (start)',
            'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_logifre_with_its_own_config',
                'logfire.msg_template': 'child',
                'logfire.msg': 'child',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '1',
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
                'logfire.level': 'info',
                'logfire.msg_template': 'test1',
                'logfire.msg': 'test1',
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_logifre_with_its_own_config',
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
                'logfire.level': 'info',
                'logfire.msg_template': 'test2',
                'logfire.msg': 'test2',
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_logifre_with_its_own_config',
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
                'code.function': 'test_logifre_with_its_own_config',
                'logfire.msg_template': 'child',
                'logfire.msg': 'child',
                'logfire.span_type': 'span',
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
                'code.function': 'test_logifre_with_its_own_config',
                'logfire.msg_template': 'root',
                'logfire.msg': 'root',
                'logfire.span_type': 'span',
            },
        },
    ]


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

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'main (start)',
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
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'child (start)',
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
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '1',
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
                'logfire.msg': 'child',
                'logfire.span_type': 'span',
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
                'logfire.msg': 'main',
                'logfire.span_type': 'span',
            },
        },
    ]


def test_span_in_executor_args(exporter: TestExporter) -> None:
    with ThreadPoolExecutor() as exec:
        exec.submit(do_work_with_arg, 'foo')
        exec.shutdown(wait=True)

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'child {within} (start)',
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
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
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
                'logfire.msg': 'child foo',
                'logfire.span_type': 'span',
            },
        },
    ]


def test_format_attribute_added_after_start_span_sent(exporter: TestExporter) -> None:
    with logfire.span('{missing}') as s:
        s.set_attribute('missing', 'value')

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': '{missing} (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_format_attribute_added_after_start_span_sent',
                'logfire.msg_template': '{missing}',
                'logfire.msg': '...',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': '{missing}',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_format_attribute_added_after_start_span_sent',
                'logfire.msg_template': '{missing}',
                'logfire.span_type': 'span',
                'missing': 'value',
                'logfire.msg': 'value',
            },
        },
    ]

    with pytest.warns(UserWarning, match=r'missing') as warnings:
        with logfire.span('{missing}') as s:
            pass

    assert len(warnings) == 1
    assert warnings[0].filename == __file__


def check_project_name(expected_project_name: str) -> None:
    from logfire._config import GLOBAL_CONFIG

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
    configure(send_to_logfire=False, console=ConsoleOptions(enabled=False), project_name='foobar!')

    with executor_factory() as executor:
        executor.submit(check_project_name, 'foobar!')
        executor.shutdown(wait=True)


def test_kwarg_with_dot_in_name(exporter: TestExporter) -> None:
    logfire.info('{http.status}', **{'http.status': 123})

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': '123',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'info',
                'logfire.msg_template': '{http.status}',
                'logfire.msg': '123',
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_kwarg_with_dot_in_name',
                'http.status': 123,
            },
        }
    ]

    exporter.exported_spans.clear()

    with logfire.span('{http.status} - {code.lineno}', **{'http.status': 123}):
        pass

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': '{http.status} - {code.lineno} (start)',
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
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
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
            },
        },
    ]


def test_large_int(exporter: TestExporter) -> None:
    with logfire.span(
        'test {larger_int=} {max_int=} {small_int=}', larger_int=2**256 + 1, max_int=2**63, small_int=2**63 - 1
    ):
        pass

    # check the encoded spans, this is where the value used to get dropped before we encoded them as strings
    span = encode_spans(exporter.exported_spans)
    attributes = span.resource_spans[0].scope_spans[0].spans[0].attributes
    for attr in attributes:
        if attr.key == 'larger_int__LARGE_INT':
            assert (
                attr.value.string_value
                == '115792089237316195423570985008687907853269984665640564039457584007913129639937'
            )
        elif attr.key == 'max_int__LARGE_INT':
            assert attr.value.string_value == '9223372036854775808'
    span.SerializeToString()  # make sure there's no errors converting the spans to a binary message

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'test {larger_int=} {max_int=} {small_int=}',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_large_int',
                'larger_int__LARGE_INT': '115792089237316195423570985008687907853269984665640564039457584007913129639937',
                'max_int__LARGE_INT': '9223372036854775808',
                'small_int': 9223372036854775807,
                'logfire.msg_template': 'test {larger_int=} {max_int=} {small_int=}',
                'logfire.span_type': 'span',
                'logfire.msg': 'test larger_int=115792089237316195423570985008687907853269984665640564039457584007913129639937 max_int=9223372036854775808 small_int=9223372036854775807',
            },
        }
    ]


def test_with_tags_as_context_manager(exporter: TestExporter) -> None:
    with logfire.span('1'):
        with logfire.with_tags('tag1', 'tag2') as tagged:
            with logfire.span('2'):
                pass

    with logfire.span('3'):
        with logfire.with_tags('tag3', 'tag4'):
            with logfire.span('4'):
                with tagged.span('5'):
                    pass

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': '2',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_with_tags_as_context_manager',
                'logfire.msg_template': '2',
                'logfire.tags': ('tag1', 'tag2'),
                'logfire.span_type': 'span',
                'logfire.msg': '2',
            },
        },
        {
            'name': '1',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 4000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_with_tags_as_context_manager',
                'logfire.msg_template': '1',
                'logfire.span_type': 'span',
                'logfire.msg': '1',
            },
        },
        {
            'name': '5',
            'context': {'trace_id': 2, 'span_id': 9, 'is_remote': False},
            'parent': {'trace_id': 2, 'span_id': 7, 'is_remote': False},
            'start_time': 7000000000,
            'end_time': 8000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_with_tags_as_context_manager',
                'logfire.msg_template': '5',
                'logfire.tags': ('tag3', 'tag4', 'tag1', 'tag2'),
                'logfire.span_type': 'span',
                'logfire.msg': '5',
            },
        },
        {
            'name': '4',
            'context': {'trace_id': 2, 'span_id': 7, 'is_remote': False},
            'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
            'start_time': 6000000000,
            'end_time': 9000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_with_tags_as_context_manager',
                'logfire.msg_template': '4',
                'logfire.tags': ('tag3', 'tag4'),
                'logfire.span_type': 'span',
                'logfire.msg': '4',
            },
        },
        {
            'name': '3',
            'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
            'parent': None,
            'start_time': 5000000000,
            'end_time': 10000000000,
            'attributes': {
                'code.filepath': 'test_logfire.py',
                'code.lineno': 123,
                'code.function': 'test_with_tags_as_context_manager',
                'logfire.msg_template': '3',
                'logfire.span_type': 'span',
                'logfire.msg': '3',
            },
        },
    ]
