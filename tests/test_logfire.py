from __future__ import annotations

import inspect
import re
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from functools import partial
from logging import getLogger
from typing import Any, Callable
from unittest.mock import patch

import pytest
from dirty_equals import IsInt, IsJson, IsStr
from inline_snapshot import Is, snapshot
from opentelemetry.metrics import get_meter
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.trace import INVALID_SPAN, StatusCode, get_current_span, get_tracer
from pydantic import BaseModel, __version__ as pydantic_version
from pydantic_core import ValidationError

import logfire
from logfire import Logfire, suppress_instrumentation
from logfire._internal.config import LogfireConfig, LogfireNotConfiguredWarning, configure
from logfire._internal.constants import (
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    ATTRIBUTES_TAGS_KEY,
    LEVEL_NUMBERS,
    LevelName,
)
from logfire._internal.formatter import FormattingFailedWarning, InspectArgumentsFailedWarning
from logfire._internal.main import NoopSpan
from logfire._internal.tracer import record_exception
from logfire._internal.utils import SeededRandomIdGenerator, is_instrumentation_suppressed
from logfire.integrations.logging import LogfireLoggingHandler
from logfire.testing import TestExporter
from tests.test_metrics import get_collected_metrics


@pytest.mark.parametrize('method', ['trace', 'info', 'debug', 'warn', 'warning', 'error', 'fatal'])
def test_log_methods_without_kwargs(method: str):
    with pytest.warns(FormattingFailedWarning) as warnings:
        getattr(logfire, method)('{foo}', bar=2)

    [warning] = warnings
    assert warning.filename.endswith('test_logfire.py')
    assert str(warning.message) == snapshot("""\

    Ensure you are either:
      (1) passing an f-string directly, with inspect_arguments enabled and working, or
      (2) passing a literal `str.format`-style template, not a preformatted string.
    See https://logfire.pydantic.dev/docs/guides/onboarding-checklist/add-manual-tracing/#messages-and-span-names.
    The problem was: The field {foo} is not defined.\
""")


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


def test_instrument_with_no_parameters(exporter: TestExporter) -> None:
    @logfire.instrument
    def foo(x: int):
        return x * 2

    assert foo(2) == 4
    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_with_no_parameters.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.function': 'test_instrument_with_no_parameters.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_with_no_parameters.<locals>.foo',
                    'code.lineno': 123,
                    'code.filepath': 'test_logfire.py',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_with_no_parameters.<locals>.foo',
                    'logfire.json_schema': '{"type":"object","properties":{"x":{}}}',
                    'x': 2,
                    'logfire.span_type': 'span',
                },
            }
        ]
    )


def test_instrument_func_with_no_params(exporter: TestExporter) -> None:
    @logfire.instrument()
    def foo():
        return 4

    assert foo() == 4
    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_func_with_no_params.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_instrument_func_with_no_params.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_func_with_no_params.<locals>.foo',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_func_with_no_params.<locals>.foo',
                },
            }
        ]
    )


def test_instrument_extract_args_list(exporter: TestExporter) -> None:
    @logfire.instrument(extract_args=['a', 'b'])
    def foo(a: int, b: int, c: int):
        return a + b + c

    assert foo(1, 2, 3) == 6
    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_extract_args_list.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_instrument_extract_args_list.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_extract_args_list.<locals>.foo',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_extract_args_list.<locals>.foo',
                    'a': 1,
                    'b': 2,
                    'logfire.json_schema': '{"type":"object","properties":{"a":{},"b":{}}}',
                },
            }
        ]
    )


def test_instrument_missing_all_extract_args(exporter: TestExporter) -> None:
    def foo():
        return 4

    with pytest.warns(UserWarning) as warnings:
        foo = logfire.instrument(extract_args='bar')(foo)

    assert len(warnings) == 1
    assert str(warnings[0].message) == snapshot('Ignoring missing arguments to extract: bar')
    assert warnings[0].lineno == inspect.currentframe().f_lineno - 4  # type: ignore

    assert foo() == 4
    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_missing_all_extract_args.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_instrument_missing_all_extract_args.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_missing_all_extract_args.<locals>.foo',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_missing_all_extract_args.<locals>.foo',
                },
            }
        ]
    )


def test_instrument_missing_some_extract_args(exporter: TestExporter) -> None:
    def foo(a: int, d: int, e: int):
        return a + d + e

    with pytest.warns(UserWarning) as warnings:
        foo = logfire.instrument(extract_args=['a', 'b', 'c'])(foo)

    assert len(warnings) == 1
    assert str(warnings[0].message) == snapshot('Ignoring missing arguments to extract: b, c')
    assert warnings[0].lineno == inspect.currentframe().f_lineno - 4  # type: ignore

    assert foo(1, 2, 3) == 6
    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_missing_some_extract_args.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_instrument_missing_some_extract_args.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_missing_some_extract_args.<locals>.foo',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_missing_some_extract_args.<locals>.foo',
                    'a': 1,
                    'logfire.json_schema': '{"type":"object","properties":{"a":{}}}',
                },
            }
        ]
    )


def test_instrument_missing_template_field():
    @logfire.instrument('{foo}')
    def home(bar: str):
        return bar

    with pytest.warns(FormattingFailedWarning, match='The field {foo} is not defined.') as warnings:
        assert home('baz') == 'baz'

    warning = warnings.pop()
    assert warning.filename.endswith('test_logfire.py'), (warning.filename, warning.lineno)


def test_span_missing_template_field() -> None:
    with pytest.warns(FormattingFailedWarning, match='The field {foo} is not defined.') as warnings:
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
                'name': 'test span',
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
                'name': 'test parent span',
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
                'name': 'test child span',
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
                'name': 'test span',
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
                'name': 'test {name=} {number}',
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


@pytest.mark.parametrize('level', ('fatal', 'debug', 'error', 'info', 'notice', 'warn', 'warning', 'trace'))
def test_log(exporter: TestExporter, level: LevelName):
    getattr(logfire, level)('test {name} {number} {none}', name='foo', number=2, none=None)

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test {name} {number} {none}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': Is(LEVEL_NUMBERS[level]),
                    'logfire.msg_template': 'test {name} {number} {none}',
                    'logfire.msg': 'test foo 2 None',
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_log',
                    'name': 'foo',
                    'number': 2,
                    'none': 'null',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"number":{},"none":{"type":"null"}}}',
                },
            }
        ]
    )


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
    tagged = logfire.with_tags('test_instrument')

    @tagged.instrument('hello-world {a=}', record_return=True)
    def hello_world(a: int) -> str:
        return f'hello {a}'

    assert hello_world(123) == 'hello 123'

    assert exporter.exported_spans_as_dict(_include_pending_spans=True, _strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'hello-world {a=}',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.lineno': 123,
                    'code.function': 'test_instrument.<locals>.hello_world',
                    'a': 123,
                    'logfire.tags': ('test_instrument',),
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
                    'logfire.tags': ('test_instrument',),
                    'logfire.msg_template': 'hello-world {a=}',
                    'logfire.json_schema': '{"type":"object","properties":{"a":{},"return":{}}}',
                    'logfire.span_type': 'span',
                    'return': 'hello 123',
                    'logfire.msg': 'hello-world a=123',
                },
            },
        ]
    )


def test_instrument_other_callable(exporter: TestExporter):
    class Instrumented:
        def __call__(self, a: int) -> str:
            return f'hello {a}'

        def __repr__(self):
            return '<Instrumented>'

    inst = logfire.instrument()(Instrumented())

    assert inst(456) == 'hello 456'

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_other_callable.<locals>.Instrumented.__call__',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.function': 'test_instrument_other_callable.<locals>.Instrumented.__call__',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_other_callable.<locals>.Instrumented.__call__',
                    'code.lineno': 123,
                    'code.filepath': 'test_logfire.py',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_other_callable.<locals>.Instrumented.__call__',
                    'logfire.json_schema': '{"type":"object","properties":{"a":{}}}',
                    'a': 456,
                    'logfire.span_type': 'span',
                },
            }
        ]
    )


@pytest.mark.anyio
async def test_instrument_async_generator_warning(exporter: TestExporter):
    async def foo():
        yield 1

    inst = logfire.instrument()

    with pytest.warns(UserWarning) as warnings:
        foo = inst(foo)

    assert len(warnings) == 1
    assert str(warnings[0].message) == snapshot(
        '@logfire.instrument should only be used on generators if they are used as context managers. '
        'See https://logfire.pydantic.dev/docs/guides/advanced/generators/#using-logfireinstrument for more information.'
    )
    assert warnings[0].filename.endswith('test_logfire.py')
    assert warnings[0].lineno == inspect.currentframe().f_lineno - 8  # type: ignore
    assert foo.__name__ == 'foo'

    assert [value async for value in foo()] == [1]

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_async_generator_warning.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.function': 'test_instrument_async_generator_warning.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_async_generator_warning.<locals>.foo',
                    'code.lineno': 123,
                    'code.filepath': 'test_logfire.py',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_async_generator_warning.<locals>.foo',
                    'logfire.span_type': 'span',
                },
            }
        ]
    )


def test_instrument_generator_warning(exporter: TestExporter):
    def foo():
        yield 1

    inst = logfire.instrument()

    with pytest.warns(UserWarning) as warnings:
        foo = inst(foo)

    assert len(warnings) == 1
    assert str(warnings[0].message) == snapshot(
        '@logfire.instrument should only be used on generators if they are used as context managers. '
        'See https://logfire.pydantic.dev/docs/guides/advanced/generators/#using-logfireinstrument for more information.'
    )
    assert warnings[0].filename.endswith('test_logfire.py')
    assert warnings[0].lineno == inspect.currentframe().f_lineno - 8  # type: ignore
    assert foo.__name__ == 'foo'

    assert list(foo()) == [1]

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_generator_warning.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.function': 'test_instrument_generator_warning.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_generator_warning.<locals>.foo',
                    'code.lineno': 123,
                    'code.filepath': 'test_logfire.py',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_generator_warning.<locals>.foo',
                    'logfire.span_type': 'span',
                },
            }
        ]
    )


def test_instrument_contextmanager_warning(exporter: TestExporter):
    @contextmanager
    def foo():
        yield

    inst = logfire.instrument()

    with pytest.warns(UserWarning) as warnings:
        foo = inst(foo)

    assert len(warnings) == 1
    assert str(warnings[0].message) == snapshot(
        '@logfire.instrument should be underneath @contextlib.[async]contextmanager so that it is applied first.'
    )
    assert warnings[0].filename.endswith('test_logfire.py')
    assert warnings[0].lineno == inspect.currentframe().f_lineno - 7  # type: ignore

    with foo():
        logfire.info('hello')

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_contextmanager_warning.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.function': 'test_instrument_contextmanager_warning.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_contextmanager_warning.<locals>.foo',
                    'code.lineno': 123,
                    'code.filepath': 'test_logfire.py',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_contextmanager_warning.<locals>.foo',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'hello',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hello',
                    'logfire.msg': 'hello',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_instrument_contextmanager_warning',
                    'code.lineno': 123,
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_instrument_asynccontextmanager_warning(exporter: TestExporter):
    @asynccontextmanager
    async def foo():
        yield

    inst = logfire.instrument()

    with pytest.warns(UserWarning) as warnings:
        foo = inst(foo)

    assert len(warnings) == 1
    assert str(warnings[0].message) == snapshot(
        '@logfire.instrument should be underneath @contextlib.[async]contextmanager so that it is applied first.'
    )
    assert warnings[0].filename.endswith('test_logfire.py')
    assert warnings[0].lineno == inspect.currentframe().f_lineno - 7  # type: ignore

    async with foo():
        logfire.info('hello')

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_asynccontextmanager_warning.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.function': 'test_instrument_asynccontextmanager_warning.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_asynccontextmanager_warning.<locals>.foo',
                    'code.lineno': 123,
                    'code.filepath': 'test_logfire.py',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_asynccontextmanager_warning.<locals>.foo',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'hello',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hello',
                    'logfire.msg': 'hello',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_instrument_asynccontextmanager_warning',
                    'code.lineno': 123,
                },
            },
        ]
    )


def test_instrument_contextmanager_prevent_warning(exporter: TestExporter):
    @contextmanager
    @logfire.instrument(allow_generator=True)
    def foo():
        yield

    assert foo.__name__ == 'foo'

    with foo():
        logfire.info('hello')

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'hello',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.function': 'test_instrument_contextmanager_prevent_warning',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hello',
                    'code.lineno': 123,
                    'code.filepath': 'test_logfire.py',
                    'logfire.msg': 'hello',
                    'logfire.span_type': 'log',
                },
            },
            {
                'name': 'Calling tests.test_logfire.test_instrument_contextmanager_prevent_warning.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_contextmanager_prevent_warning.<locals>.foo',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_contextmanager_prevent_warning.<locals>.foo',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_instrument_contextmanager_prevent_warning.<locals>.foo',
                    'code.lineno': 123,
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_instrument_asynccontextmanager_prevent_warning(exporter: TestExporter):
    @asynccontextmanager
    @logfire.instrument(allow_generator=True)
    async def foo():
        yield

    assert foo.__name__ == 'foo'

    async with foo():
        logfire.info('hello')

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'hello',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.function': 'test_instrument_asynccontextmanager_prevent_warning',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hello',
                    'code.lineno': 123,
                    'code.filepath': 'test_logfire.py',
                    'logfire.msg': 'hello',
                    'logfire.span_type': 'log',
                },
            },
            {
                'name': 'Calling tests.test_logfire.test_instrument_asynccontextmanager_prevent_warning.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_asynccontextmanager_prevent_warning.<locals>.foo',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_asynccontextmanager_prevent_warning.<locals>.foo',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_instrument_asynccontextmanager_prevent_warning.<locals>.foo',
                    'code.lineno': 123,
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_instrument_async(exporter: TestExporter):
    @logfire.instrument
    async def foo():
        return 456

    assert foo.__name__ == 'foo'
    assert await foo() == 456

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_async.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.function': 'test_instrument_async.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_async.<locals>.foo',
                    'code.lineno': 123,
                    'code.filepath': 'test_logfire.py',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_async.<locals>.foo',
                    'logfire.span_type': 'span',
                },
            }
        ]
    )


@pytest.mark.anyio
async def test_instrument_async_record_return(exporter: TestExporter):
    @logfire.instrument(record_return=True)
    async def foo():
        return 456

    assert foo.__name__ == 'foo'
    assert await foo() == 456

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'name': 'Calling tests.test_logfire.test_instrument_async_record_return.<locals>.foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.function': 'test_instrument_async_record_return.<locals>.foo',
                    'logfire.msg_template': 'Calling tests.test_logfire.test_instrument_async_record_return.<locals>.foo',
                    'code.lineno': 123,
                    'code.filepath': 'test_logfire.py',
                    'logfire.msg': 'Calling tests.test_logfire.test_instrument_async_record_return.<locals>.foo',
                    'logfire.span_type': 'span',
                    'return': 456,
                    'logfire.json_schema': '{"type":"object","properties":{"return":{}}}',
                },
            }
        ]
    )


def test_instrument_extract_false(exporter: TestExporter):
    @logfire.instrument('hello {a}!', extract_args=False)
    def hello_world(a: int) -> str:
        return f'hello {a}'

    assert hello_world.__name__ == 'hello_world'

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
                            'exception.type': 'pydantic_core._pydantic_core.ValidationError',
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
                            'exception.type': 'pydantic_core._pydantic_core.ValidationError',
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


def test_logfire_with_its_own_config(exporter: TestExporter, config_kwargs: dict[str, Any]) -> None:
    exporter1 = TestExporter()
    config_kwargs.update(additional_span_processors=[SimpleSpanProcessor(exporter1)])
    config = LogfireConfig(**config_kwargs)

    logfire = Logfire(config=config)
    logfire1 = logfire.with_tags('tag1', 'tag2')

    with pytest.warns(LogfireNotConfiguredWarning) as warnings:
        with logfire.span('root'):
            with logfire.span('child'):
                logfire.info('test1')
                logfire1.info('test2')

    assert str(warnings[0].message) == (
        'No logs or spans will be created until `logfire.configure()` has been called. '
        'Set the environment variable LOGFIRE_IGNORE_NO_CONFIG=1 or add ignore_no_config=true in pyproject.toml to suppress this warning.'
    )
    assert warnings[0].lineno == inspect.currentframe().f_lineno - 9  # type: ignore

    with pytest.warns(LogfireNotConfiguredWarning) as warnings:
        logfire.instrument_django()

    assert str(warnings[0].message) == (
        'Instrumentation will have no effect until `logfire.configure()` has been '
        'called. Set the environment variable LOGFIRE_IGNORE_NO_CONFIG=1 or add ignore_no_config=true in pyproject.toml to suppress '
        'this warning.'
    )
    assert warnings[0].lineno == inspect.currentframe().f_lineno - 7  # type: ignore

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot([])
    assert exporter1.exported_spans_as_dict(_include_pending_spans=True) == snapshot([])

    config.initialize()
    with logfire.span('root'):
        with logfire.span('child'):
            logfire.info('test1')
            logfire1.info('test2')

    assert exporter1.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'root',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 5000000000,
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
                'name': 'child',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 6000000000,
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
                'start_time': 7000000000,
                'end_time': 7000000000,
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
                'start_time': 8000000000,
                'end_time': 8000000000,
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
                'start_time': 6000000000,
                'end_time': 9000000000,
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
                'start_time': 5000000000,
                'end_time': 10000000000,
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
                'name': 'main',
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
                'name': 'child',
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
                'name': 'child {within}',
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
                    'e': 'null',
                    'f': 'null',
                    'logfire.json_schema': '{"type":"object","properties":{"a":{"type":"object"},"c":{"type":"object"},"e":{"type":"null"},"f":{"type":"null"}}}',
                },
            }
        ]
    )


def test_format_attribute_added_after_pending_span_sent(exporter: TestExporter) -> None:
    with pytest.warns(FormattingFailedWarning, match=r'missing') as warnings:
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
                'name': '{present} {missing}',
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
                    'logfire.msg': '{present} {missing}',
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
                    'logfire.msg': '{present} {missing}',
                    'logfire.json_schema': '{"type":"object","properties":{"present":{},"missing":{}}}',
                    'logfire.span_type': 'span',
                    'missing': 'value',
                },
            },
        ]
    )


def check_service_name(expected_service_name: str) -> None:
    from logfire._internal.config import GLOBAL_CONFIG

    assert GLOBAL_CONFIG.service_name == expected_service_name


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
        service_name='foobar!',
        metrics=logfire.MetricsOptions(additional_readers=[InMemoryMetricReader()]),
    )

    with executor_factory() as executor:
        executor.submit(check_service_name, 'foobar!')
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
                'name': '{http.status} - {code.lineno}',
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


@pytest.mark.parametrize('method', ('trace', 'debug', 'info', 'notice', 'warn', 'warning', 'error', 'fatal', 'span'))
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
                'name': 'test {value=}',
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
                'name': 'test {value=}',
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
                'name': 'test {value=}',
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


def test_tags_setter_basic_operations():
    with logfire.span('foo') as span:
        span.tags = ('a', 'b')
        assert span.tags == ('a', 'b')

        # Only unique tags are kept
        span.tags += ('a',)
        assert span.tags == ('a', 'b')

        # Adding new tags
        span.tags += ('c',)
        assert span.tags == ('a', 'b', 'c')

        span.tags += ('d',)
        assert span.tags == ('a', 'b', 'c', 'd')


def test_tags_setter_empty_tags_returns_empty_tuple():
    with logfire.span('foo') as span:
        assert span.tags == ()


def test_tags_setter_with_non_initialized_span() -> None:
    span = logfire.with_tags('tag1', 'tag2').span('test span')
    assert span.tags == ('tag1', 'tag2')

    # Set tags using the setter with self._span not yet created
    span.tags = ('tag3', 'tag4')
    assert span.tags == ('tag3', 'tag4')

    # Call __enter__ to initialize _span, check that tags remain unchanged
    with span:
        assert span.tags == ('tag3', 'tag4')

    # Check that tags remain unchanged
    assert span.tags == ('tag3', 'tag4')


def test_tags_setter_valid_type_extensions() -> None:
    span = logfire.span('test span')

    # Check default tags value is empty tuple
    assert span.tags == ()

    # Setting tags with a list should work
    span.tags = ['tag1', 'tag2']
    assert span.tags == ('tag1', 'tag2')

    # Setting tags with a string should work
    span.tags = 'bar'
    assert span.tags == ('bar',)


def test_tags_setter_invalid_type_extensions() -> None:
    span = logfire.span('test span')
    assert span.tags == ()

    # Setting tags with a non-iterable type should raise an error, unless it's a string
    with pytest.raises(TypeError, match="'int' object is not iterable"):
        span.tags = 123  # type: ignore

    # Setting tags using the += operator with a non-tuple type should raise an error, including for lists
    with pytest.raises(TypeError, match=r'can only concatenate tuple \(not \"list\"\) to tuple'):
        span.tags += ['tag3']  # type: ignore


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

    for span in exporter.exported_spans[:-3]:
        assert span.status.description is None

    for span in exporter.exported_spans[-3:]:
        assert span.status.status_code == StatusCode.ERROR
        assert span.status.description == 'ValueError: an error'


def test_span_level(exporter: TestExporter):
    with logfire.span('foo', _level='debug') as span:
        span.set_level('warn')

    # debug when pending, warn when finished
    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'foo',
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
                'name': 'foo',
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


def test_span_links(exporter: TestExporter):
    with logfire.span('first span') as span:
        first_context = span.context

    with logfire.span('second span') as span:
        second_context = span.context

    assert first_context
    assert second_context
    with logfire.span('foo', _links=[(first_context, None)]) as span:
        span.add_link(second_context)

    assert exporter.exported_spans_as_dict(_include_pending_spans=True)[-2:] == snapshot(
        [
            {
                'name': 'foo',
                'context': {'trace_id': 3, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_span_links',
                    'code.lineno': 123,
                    'logfire.msg_template': 'foo',
                    'logfire.msg': 'foo',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
                'links': [{'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False}, 'attributes': {}}],
            },
            {
                'name': 'foo',
                'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_span_links',
                    'code.lineno': 123,
                    'logfire.msg_template': 'foo',
                    'logfire.msg': 'foo',
                    'logfire.span_type': 'span',
                },
                'links': [
                    {
                        'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                        'attributes': {},
                    },
                    {
                        'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                        'attributes': {},
                    },
                ],
            },
        ]
    )


def test_span_add_link_before_start(exporter: TestExporter):
    with logfire.span('first span') as span:
        context = span.context

    assert context
    span = logfire.span('foo')
    span.add_link(context)

    with span:
        pass

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'first span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_span_add_link_before_start',
                    'code.lineno': 123,
                    'logfire.msg_template': 'first span',
                    'logfire.msg': 'first span',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'foo',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_span_add_link_before_start',
                    'code.lineno': 123,
                    'logfire.msg_template': 'foo',
                    'logfire.msg': 'foo',
                    'logfire.span_type': 'span',
                },
                'links': [
                    {
                        'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                        'attributes': {},
                    }
                ],
            },
        ]
    )


GLOBAL_VAR = 1


@pytest.mark.skipif(sys.version_info < (3, 9), reason='f-string magic is disabled in Python 3.8')
def test_inspect_arguments(exporter: TestExporter):
    local_var = 2
    x = 1.2345

    # Test some cases that require `executing` (i.e. the simple fallback heuristics can't handle)
    # particularly two `span` calls in one line.
    with logfire.span(f'span {GLOBAL_VAR} {local_var}'), logfire.span(f'span2 {local_var}'):
        str(logfire.info(f'log {GLOBAL_VAR} {local_var}'))

    # Test that an attribute overrides a local variable
    logfire.info(f'log2 {local_var}', local_var=3, x=x)

    # Test the .log method which has the argument in a different place from the other methods.
    logfire.log('error', f'log3 {GLOBAL_VAR}')
    logfire.log(level='error', msg_template=f'log4 {GLOBAL_VAR}')

    # Test putting exotic things inside braces.
    # Note that the span name / message template differ slightly from the f-string in these cases.
    logfire.info(f'log5 {local_var = }')
    logfire.info(f'log6 {x:.{local_var}f}')
    logfire.info(f'log7 {str(local_var)!r}')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'log {GLOBAL_VAR} {local_var}',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'log {GLOBAL_VAR} {local_var}',
                    'logfire.msg': f'log {GLOBAL_VAR} {local_var}',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_inspect_arguments',
                    'code.lineno': 123,
                    'GLOBAL_VAR': 1,
                    'local_var': 2,
                    'logfire.json_schema': '{"type":"object","properties":{"GLOBAL_VAR":{},"local_var":{}}}',
                },
            },
            {
                'name': 'span2 {local_var}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_inspect_arguments',
                    'code.lineno': 123,
                    'local_var': 2,
                    'logfire.msg_template': 'span2 {local_var}',
                    'logfire.msg': f'span2 {local_var}',
                    'logfire.json_schema': '{"type":"object","properties":{"local_var":{}}}',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'span {GLOBAL_VAR} {local_var}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_inspect_arguments',
                    'code.lineno': 123,
                    'GLOBAL_VAR': 1,
                    'local_var': 2,
                    'logfire.msg_template': 'span {GLOBAL_VAR} {local_var}',
                    'logfire.msg': f'span {GLOBAL_VAR} {local_var}',
                    'logfire.json_schema': '{"type":"object","properties":{"GLOBAL_VAR":{},"local_var":{}}}',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'log2 {local_var}',
                'context': {'trace_id': 2, 'span_id': 6, 'is_remote': False},
                'parent': None,
                'start_time': 6000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'log2 {local_var}',
                    'logfire.msg': 'log2 3',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_inspect_arguments',
                    'code.lineno': 123,
                    'local_var': 3,
                    'x': 1.2345,
                    'logfire.json_schema': '{"type":"object","properties":{"local_var":{},"x":{}}}',
                },
            },
            {
                'name': 'log3 {GLOBAL_VAR}',
                'context': {'trace_id': 3, 'span_id': 7, 'is_remote': False},
                'parent': None,
                'start_time': 7000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'log3 {GLOBAL_VAR}',
                    'logfire.msg': f'log3 {GLOBAL_VAR}',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_inspect_arguments',
                    'code.lineno': 123,
                    'GLOBAL_VAR': 1,
                    'logfire.json_schema': '{"type":"object","properties":{"GLOBAL_VAR":{}}}',
                },
            },
            {
                'name': 'log4 {GLOBAL_VAR}',
                'context': {'trace_id': 4, 'span_id': 8, 'is_remote': False},
                'parent': None,
                'start_time': 8000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'log4 {GLOBAL_VAR}',
                    'logfire.msg': f'log4 {GLOBAL_VAR}',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_inspect_arguments',
                    'code.lineno': 123,
                    'GLOBAL_VAR': 1,
                    'logfire.json_schema': '{"type":"object","properties":{"GLOBAL_VAR":{}}}',
                },
            },
            {
                'name': 'log5 local_var = {local_var}',
                'context': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 9000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'log5 local_var = {local_var}',
                    'logfire.msg': f'log5 {local_var = }',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_inspect_arguments',
                    'code.lineno': 123,
                    'local_var': 2,
                    'logfire.json_schema': '{"type":"object","properties":{"local_var":{}}}',
                },
            },
            {
                'name': 'log6 {x}',
                'context': {'trace_id': 6, 'span_id': 10, 'is_remote': False},
                'parent': None,
                'start_time': 10000000000,
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'log6 {x}',
                    'logfire.msg': f'log6 {x:.{local_var}f}',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_inspect_arguments',
                    'code.lineno': 123,
                    'x': 1.2345,
                    'logfire.json_schema': '{"type":"object","properties":{"x":{}}}',
                },
            },
            {
                'name': 'log7 {str(local_var)}',
                'context': {'trace_id': 7, 'span_id': 11, 'is_remote': False},
                'parent': None,
                'start_time': 11000000000,
                'end_time': 11000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'log7 {str(local_var)}',
                    'logfire.msg': f'log7 {str(local_var)!r}',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_inspect_arguments',
                    'code.lineno': 123,
                    'str(local_var)': '2',
                    'logfire.json_schema': '{"type":"object","properties":{"str(local_var)":{}}}',
                },
            },
        ]
    )


@pytest.mark.skipif(sys.version_info < (3, 11), reason='Testing behaviour in Python 3.11+')
def test_executing_failure(exporter: TestExporter, monkeypatch: pytest.MonkeyPatch):
    # We're about to 'disable' `executing` which `snapshot` also uses, so make the snapshot first.
    expected_spans = snapshot(
        [
            {
                'name': 'good log {local_var}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'good log {local_var}',
                    'logfire.msg': 'good log 3',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_executing_failure',
                    'code.lineno': 123,
                    'things': '[]',
                    'local_var': 3,
                    'logfire.json_schema': '{"type":"object","properties":{"things":{"type":"array","x-python-datatype":"set"},"local_var":{}}}',
                },
            },
            {
                'name': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
`executing` failed to find a node.\
""",
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
`executing` failed to find a node.\
""",
                    'logfire.msg': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
`executing` failed to find a node.\
""",
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_executing_failure',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'bad log 3',
                'context': {'trace_id': 3, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'bad log 3',
                    'logfire.msg': 'bad log 3',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_executing_failure',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'good span {local_var}',
                'context': {'trace_id': 4, 'span_id': 4, 'is_remote': False},
                'parent': None,
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_executing_failure',
                    'code.lineno': 123,
                    'local_var': 3,
                    'logfire.msg_template': 'good span {local_var}',
                    'logfire.msg': 'good span 3',
                    'logfire.json_schema': '{"type":"object","properties":{"local_var":{}}}',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
`executing` failed to find a node.\
""",
                'context': {'trace_id': 5, 'span_id': 6, 'is_remote': False},
                'parent': None,
                'start_time': 6000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
`executing` failed to find a node.\
""",
                    'logfire.msg': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
`executing` failed to find a node.\
""",
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_executing_failure',
                    'code.lineno': 123,
                },
            },
            {
                'name': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
`executing` failed to find a node.\
""",
                'context': {'trace_id': 6, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 6, 'span_id': 7, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
`executing` failed to find a node.\
""",
                    'logfire.msg': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
`executing` failed to find a node.\
""",
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_executing_failure',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'bad span 2 3',
                'context': {'trace_id': 6, 'span_id': 10, 'is_remote': False},
                'parent': {'trace_id': 6, 'span_id': 7, 'is_remote': False},
                'start_time': 9000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_executing_failure',
                    'code.lineno': 123,
                    'logfire.msg_template': 'bad span 2 3',
                    'logfire.msg': 'bad span 2 3',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'bad span 1 3',
                'context': {'trace_id': 6, 'span_id': 7, 'is_remote': False},
                'parent': None,
                'start_time': 7000000000,
                'end_time': 11000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_executing_failure',
                    'code.lineno': 123,
                    'logfire.msg_template': 'bad span 1 3',
                    'logfire.msg': 'bad span 1 3',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )
    import executing._position_node_finder

    # Test what happens when `executing` fails.
    monkeypatch.setattr(executing._position_node_finder.PositionNodeFinder, 'find_node', lambda _: None)  # type: ignore  # pragma: no cover  (coverage being weird)

    local_var = 3
    # The simple heuristic works when there's only one call with arguments in the whole statement.
    logfire.info(f'good log {local_var}', things=set())

    with pytest.warns(InspectArgumentsFailedWarning, match='`executing` failed to find a node.$'):
        # Two calls with arguments breaks the heuristic
        str(logfire.info(f'bad log {local_var}'))

    # Works:
    with logfire.span(f'good span {local_var}'):
        pass

    with pytest.warns(InspectArgumentsFailedWarning, match='`executing` failed to find a node.$'):
        # Multiple calls break the heuristic.
        with logfire.span(f'bad span 1 {local_var}'), logfire.span(f'bad span 2 {local_var}'):
            pass

    assert exporter.exported_spans_as_dict() == expected_spans


@pytest.mark.skipif(
    sys.version_info[:2] == (3, 8), reason='Warning is only raised in Python 3.9+ because f-string magic is enabled'
)
def test_find_arg_failure(exporter: TestExporter):
    info = partial(logfire.info, 'info')
    log = partial(logfire.log, 'error', 'log')
    span = partial(logfire.span, 'span')
    with pytest.warns(
        InspectArgumentsFailedWarning, match="Couldn't identify the `msg_template` argument in the call."
    ):
        info()
    with pytest.warns(
        InspectArgumentsFailedWarning, match="Couldn't identify the `msg_template` argument in the call."
    ):
        log()
    with pytest.warns(
        InspectArgumentsFailedWarning, match="Couldn't identify the `msg_template` argument in the call."
    ):
        with span():
            pass

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
Couldn't identify the `msg_template` argument in the call.\
""",
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
Couldn't identify the `msg_template` argument in the call.\
""",
                    'logfire.msg': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
Couldn't identify the `msg_template` argument in the call.\
""",
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_find_arg_failure',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'info',
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'info',
                    'logfire.msg': 'info',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_find_arg_failure',
                    'code.lineno': 123,
                },
            },
            {
                'name': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
Couldn't identify the `msg_template` argument in the call.\
""",
                'context': {'trace_id': 3, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
Couldn't identify the `msg_template` argument in the call.\
""",
                    'logfire.msg': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
Couldn't identify the `msg_template` argument in the call.\
""",
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_find_arg_failure',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'log',
                'context': {'trace_id': 4, 'span_id': 4, 'is_remote': False},
                'parent': None,
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'log',
                    'logfire.msg': 'log',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_find_arg_failure',
                    'code.lineno': 123,
                },
            },
            {
                'name': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
Couldn't identify the `msg_template` argument in the call.\
""",
                'context': {'trace_id': 5, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
Couldn't identify the `msg_template` argument in the call.\
""",
                    'logfire.msg': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
Couldn't identify the `msg_template` argument in the call.\
""",
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_find_arg_failure',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'span',
                'context': {'trace_id': 6, 'span_id': 6, 'is_remote': False},
                'parent': None,
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_find_arg_failure',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


@pytest.mark.skipif(sys.version_info[:2] == (3, 8), reason='fstring magic is only for 3.9+')
def test_wrong_fstring_source_segment(exporter: TestExporter):
    name = 'me'
    # This is a case where `ast.get_source_segment` returns an incorrect string for `{name}`
    # in some Python versions, hence the fallback to `ast.unparse` (so this still works).
    logfire.info(
        f"""
        Hello {name}
        """
    )
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': """\

        Hello {name}
        \
""",
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': """\

        Hello {name}
        \
""",
                    'logfire.msg': """\

        Hello me
        \
""",
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_wrong_fstring_source_segment',
                    'code.lineno': 123,
                    'name': 'me',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{}}}',
                },
            }
        ]
    )


def test_suppress_instrumentation(exporter: TestExporter):
    logfire.info('log1')
    assert not is_instrumentation_suppressed()
    with suppress_instrumentation():
        assert is_instrumentation_suppressed()
        # Not included in the asserted spans below
        logfire.info('log2')
    assert not is_instrumentation_suppressed()
    logfire.info('log3')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'log1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'log1',
                    'logfire.msg': 'log1',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_suppress_instrumentation',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'log3',
                'context': {'trace_id': 3, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'log3',
                    'logfire.msg': 'log3',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_suppress_instrumentation',
                    'code.lineno': 123,
                },
            },
        ]
    )


def test_internal_exception_span(caplog: pytest.LogCaptureFixture, exporter: TestExporter):
    with logfire.span('foo', _tags=123) as span:  # type: ignore
        # _tags=123 causes an exception (tags should be an iterable)
        assert len(caplog.records) == 1
        assert caplog.records[0].message.startswith('Caught an internal error in Logfire.')

        assert isinstance(span, NoopSpan)

        span.message = 'bar'  # this is ignored
        span.tags = 'bar'  # this is ignored

        # These methods/properties are implemented to return the right type
        assert span.is_recording() is False
        assert span.message == span.message_template == ''
        assert span.tags == ()

        # These methods exist on LogfireSpan, but NoopSpan handles them with __getattr__
        span.set_attribute('x', 1)
        span.set_level('error')
        span.record_exception(ValueError('baz'), {})

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == []


def test_internal_exception_log(caplog: pytest.LogCaptureFixture, exporter: TestExporter):
    logfire.info('foo', _tags=123)  # type: ignore

    # _tags=123 causes an exception (tags should be an iterable)
    assert len(caplog.records) == 1
    assert caplog.records[0].message.startswith('Caught an internal error in Logfire.')

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == []


def test_otel_status_code(exporter: TestExporter):
    logfire.warn('warn')
    logfire.error('error')

    assert exporter.exported_spans[0].status.status_code == StatusCode.UNSET
    assert exporter.exported_spans[1].status.status_code == StatusCode.ERROR


def test_force_flush(exporter: TestExporter):
    logfire.configure(send_to_logfire=False, console=False, additional_span_processors=[BatchSpanProcessor(exporter)])
    logfire.info('hi')

    assert not exporter.exported_spans_as_dict()

    logfire.force_flush()

    assert len(exporter.exported_spans_as_dict()) == 1


@pytest.mark.skipif(
    pydantic_version != '2.4.2',  # type: ignore
    reason='just testing compatibility with versions less that Pydantic v2.5.0',
)
def test_instrument_pydantic_on_2_5() -> None:
    with pytest.raises(RuntimeError, match='The Pydantic plugin requires Pydantic 2.5.0 or newer.'):
        logfire.instrument_pydantic()


def test_suppress_scopes(exporter: TestExporter, metrics_reader: InMemoryMetricReader):
    suppressed1 = logfire.with_settings(custom_scope_suffix='suppressed1')
    suppressed1_counter = suppressed1.metric_counter('counter1')
    suppressed1.info('before suppress')
    suppressed1_counter.add(1)

    logfire.suppress_scopes('logfire.suppressed1', 'suppressed2')

    suppressed1.info('after suppress')
    suppressed1_counter.add(10)

    suppressed2_counter = get_meter('suppressed2').create_counter('counter2')
    suppressed2_counter.add(100)

    suppressed2 = get_tracer('suppressed2')
    with logfire.span('root'):
        with suppressed2.start_as_current_span('suppressed child'):
            logfire.info('in suppressed child')

    assert exporter.exported_spans_as_dict(_include_pending_spans=True, include_instrumentation_scope=True) == snapshot(
        [
            {
                'name': 'before suppress',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'instrumentation_scope': 'logfire.suppressed1',
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'before suppress',
                    'logfire.msg': 'before suppress',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_suppress_scopes',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'root',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'instrumentation_scope': 'logfire',
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_suppress_scopes',
                    'code.lineno': 123,
                    'logfire.msg_template': 'root',
                    'logfire.msg': 'root',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'in suppressed child',
                'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 5000000000,
                'instrumentation_scope': 'logfire',
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'in suppressed child',
                    'logfire.msg': 'in suppressed child',
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_suppress_scopes',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'root',
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 7000000000,
                'instrumentation_scope': 'logfire',
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_suppress_scopes',
                    'code.lineno': 123,
                    'logfire.msg_template': 'root',
                    'logfire.msg': 'root',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )

    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'counter1',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'value': 1,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': 1,
                    'is_monotonic': True,
                },
            }
        ]
    )


def test_logfire_span_records_exceptions_once(exporter: TestExporter):
    n_calls_to_record_exception = 0

    def patched_record_exception(*args: Any, **kwargs: Any) -> Any:
        nonlocal n_calls_to_record_exception
        n_calls_to_record_exception += 1

        return record_exception(*args, **kwargs)

    with patch('logfire._internal.tracer.record_exception', patched_record_exception), patch(
        'logfire._internal.main.record_exception', patched_record_exception
    ):
        with pytest.raises(RuntimeError):
            with logfire.span('foo'):
                raise RuntimeError('error')

    assert n_calls_to_record_exception == 1
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_logfire_span_records_exceptions_once',
                    'code.lineno': 123,
                    'logfire.msg_template': 'foo',
                    'logfire.msg': 'foo',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'RuntimeError',
                            'exception.message': 'error',
                            'exception.stacktrace': 'RuntimeError: error',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            }
        ]
    )


def test_logfire_span_records_exceptions_manually_once(exporter: TestExporter):
    n_calls_to_record_exception = 0

    def patched_record_exception(*args: Any, **kwargs: Any) -> Any:
        nonlocal n_calls_to_record_exception
        n_calls_to_record_exception += 1

        return record_exception(*args, **kwargs)

    with patch('logfire._internal.tracer.record_exception', patched_record_exception), patch(
        'logfire._internal.main.record_exception', patched_record_exception
    ):
        with logfire.span('foo') as span:
            span.record_exception(RuntimeError('error'))

    assert n_calls_to_record_exception == 1
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_logfire_span_records_exceptions_manually_once',
                    'code.lineno': 123,
                    'logfire.msg_template': 'foo',
                    'logfire.msg': 'foo',
                    'logfire.span_type': 'span',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': IsInt(),
                        'attributes': {
                            'exception.type': 'RuntimeError',
                            'exception.message': 'error',
                            'exception.stacktrace': 'RuntimeError: error',
                            'exception.escaped': 'False',
                        },
                    }
                ],
            }
        ]
    )


def test_exit_ended_span(exporter: TestExporter):
    tracer = get_tracer(__name__)

    with tracer.start_span('test') as span:
        # Ensure that doing this does not emit a warning about calling end() twice when the block exits.
        span.end()

    assert exporter.exported_spans_as_dict(_strip_function_qualname=False) == snapshot(
        [
            {
                'attributes': {'logfire.msg': 'test', 'logfire.span_type': 'span'},
                'context': {'is_remote': False, 'span_id': 1, 'trace_id': 1},
                'end_time': 2000000000,
                'name': 'test',
                'parent': None,
                'start_time': 1000000000,
            }
        ]
    )


_ns_currnet_ts = 0


def incrementing_ms_ts_generator() -> int:
    global _ns_currnet_ts
    _ns_currnet_ts += 420_000  # some randon number that results in non-whole ms
    return _ns_currnet_ts // 1_000_000


@pytest.mark.parametrize(
    'id_generator',
    [SeededRandomIdGenerator(_ms_timestamp_generator=incrementing_ms_ts_generator)],
)
def test_default_id_generator(exporter: TestExporter) -> None:
    """Test that SeededRandomIdGenerator generates trace and span ids without errors."""
    for i in range(1024):
        logfire.info('log', i=i)

    exported = exporter.exported_spans_as_dict()

    # sanity check: there are 1024 trace ids
    assert len({export['context']['trace_id'] for export in exported}) == 1024
    # sanity check: there are multiple milliseconds (first 6 bytes)
    assert len({export['context']['trace_id'] >> 80 for export in exported}) == snapshot(431)

    # Check that trace ids are sortable and unique
    # We use ULIDs to generate trace ids, so they should be sortable.
    sorted_by_trace_id = [
        export['attributes']['i']
        # sort by trace_id and start_time so that if two trace ids were generated in the same ms and thus may sort randomly
        # we disambiguate with the start time
        for export in sorted(exported, key=lambda span: (span['context']['trace_id'] >> 80, span['start_time']))
    ]
    sorted_by_start_timestamp = [
        export['attributes']['i'] for export in sorted(exported, key=lambda span: span['start_time'])
    ]
    assert sorted_by_trace_id == sorted_by_start_timestamp


def test_start_end_attach_detach(exporter: TestExporter, caplog: pytest.LogCaptureFixture):
    span = logfire.span('test')
    assert not span.is_recording()
    assert not exporter.exported_spans
    assert get_current_span() is INVALID_SPAN

    span._start()  # type: ignore
    span._start()  # type: ignore
    assert span.is_recording()
    assert len(exporter.exported_spans) == 1
    assert get_current_span() is INVALID_SPAN

    span._attach()  # type: ignore
    span._attach()  # type: ignore
    assert get_current_span() is span._span  # type: ignore

    span._detach()  # type: ignore
    span._detach()  # type: ignore
    assert span.is_recording()
    assert len(exporter.exported_spans) == 1
    assert get_current_span() is INVALID_SPAN

    span._end()  # type: ignore
    span._end()  # type: ignore
    assert not span.is_recording()
    assert len(exporter.exported_spans) == 2
    assert get_current_span() is INVALID_SPAN

    assert not caplog.messages

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'test',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_start_end_attach_detach',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test',
                    'logfire.msg': 'test',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'test',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_logfire.py',
                    'code.function': 'test_start_end_attach_detach',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test',
                    'logfire.msg': 'test',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )
