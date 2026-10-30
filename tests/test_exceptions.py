import asyncio
import sys
import types
from typing import Any

import pytest
from inline_snapshot import snapshot
from opentelemetry.trace import StatusCode

import logfire
from logfire._internal.constants import ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY
from logfire._internal.exporters.test import TestExporter
from logfire._internal.utils import canonicalize_exception_traceback
from logfire.types import ExceptionCallbackHelper, LevelName


@pytest.mark.parametrize('level', [None, 'warn', 'error', 'fatal'])
@pytest.mark.parametrize('record_exception', [True, False])
def test_exception_callback_status(
    exporter: TestExporter,
    config_kwargs: dict[str, Any],
    level: LevelName | None,
    record_exception: bool,
) -> None:
    def exception_callback(helper: ExceptionCallbackHelper) -> None:
        assert helper.span.status.status_code == StatusCode.UNSET
        if level is not None:
            helper.level = level
        if not record_exception:
            helper.no_record_exception()

    # Include the default behavior without a callback.
    if level is not None or not record_exception:
        config_kwargs['advanced'].exception_callback = exception_callback
    logfire.configure(**config_kwargs)

    with pytest.raises(asyncio.CancelledError, match='test'), logfire.span('foo'):
        raise asyncio.CancelledError('test')

    (_pending, span) = exporter.exported_spans
    is_error = level != 'warn'
    assert span.status.status_code == (StatusCode.ERROR if is_error else StatusCode.UNSET)
    assert span.status.description == ('CancelledError: test' if is_error else None)
    assert span.attributes is not None
    assert span.attributes['logfire.level_num'] == {'warn': 13, 'error': 17, 'fatal': 21}[level or 'error']
    assert (ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY in span.attributes) == (is_error and record_exception)
    if record_exception:
        [event] = span.events
        assert event.name == 'exception'
        assert event.attributes is not None
        assert event.attributes['exception.type'] == 'asyncio.exceptions.CancelledError'
        assert event.attributes['exception.message'] == 'test'
        assert event.attributes['exception.escaped'] == 'True'
    else:
        assert not span.events


def test_exception_callback_set_level(exporter: TestExporter, config_kwargs: dict[str, Any]):
    def exception_callback(helper: ExceptionCallbackHelper) -> None:
        assert helper.level.name == 'error'
        assert not helper.level_is_unset
        assert helper.create_issue
        helper.level = 'warning'
        assert helper.level.name == 'warn'
        assert not helper.create_issue
        assert helper.parent_span is None
        assert isinstance(helper.exception, ValueError)
        assert helper.issue_fingerprint_source == canonicalize_exception_traceback(helper.exception)
        helper.span.set_attribute('original_fingerprint', helper.issue_fingerprint_source)

    config_kwargs['advanced'].exception_callback = exception_callback
    logfire.configure(**config_kwargs)

    with pytest.raises(ValueError):
        with logfire.span('foo'):
            raise ValueError('test')

    (_pending, span) = exporter.exported_spans
    assert span.attributes
    assert ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY not in span.attributes

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_exceptions.py',
                    'code.function': 'test_exception_callback_set_level',
                    'code.lineno': 123,
                    'logfire.msg_template': 'foo',
                    'logfire.msg': 'foo',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 13,
                    'original_fingerprint': """\

builtins.ValueError
----
tests.test_exceptions.test_exception_callback_set_level
   raise ValueError('test')\
""",
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'ValueError',
                            'exception.message': 'test',
                            'exception.stacktrace': 'ValueError: test',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            }
        ]
    )


def test_exception_nested_span(exporter: TestExporter, config_kwargs: dict[str, Any]):
    def exception_callback(helper: ExceptionCallbackHelper) -> None:
        assert helper.span.name == 'inner'
        assert helper.parent_span
        assert helper.parent_span.name == 'outer'
        assert not helper.create_issue
        helper.create_issue = True
        assert helper.create_issue

    config_kwargs['advanced'].exception_callback = exception_callback
    logfire.configure(**config_kwargs)

    with logfire.span('outer'):
        with pytest.raises(ValueError):
            with logfire.span('inner'):
                raise ValueError('test')

    span = exporter.exported_spans[2]
    assert span.name == 'inner'
    assert span.attributes
    assert span.attributes[ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY] == snapshot(
        '2d233734d60da1a16e3627ba78180e4f83a9588ab6bd365283331a1339d56072'
    )

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'inner',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_exceptions.py',
                    'code.function': 'test_exception_nested_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'inner',
                    'logfire.msg': 'inner',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 3000000000,
                        'attributes': {
                            'exception.type': 'ValueError',
                            'exception.message': 'test',
                            'exception.stacktrace': 'ValueError: test',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            },
            {
                'name': 'outer',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_exceptions.py',
                    'code.function': 'test_exception_nested_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'outer',
                    'logfire.msg': 'outer',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_set_create_issue_false(exporter: TestExporter, config_kwargs: dict[str, Any]):
    def exception_callback(helper: ExceptionCallbackHelper) -> None:
        assert helper.create_issue
        helper.create_issue = False
        assert not helper.create_issue

    config_kwargs['advanced'].exception_callback = exception_callback
    logfire.configure(**config_kwargs)

    with pytest.raises(ValueError):
        with logfire.span('foo'):
            raise ValueError('test')

    (_pending, span) = exporter.exported_spans
    assert span.attributes
    assert ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY not in span.attributes

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'foo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_exceptions.py',
                    'code.function': 'test_set_create_issue_false',
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
                            'exception.type': 'ValueError',
                            'exception.message': 'test',
                            'exception.stacktrace': 'ValueError: test',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            }
        ]
    )


def test_set_fingerprint(exporter: TestExporter, config_kwargs: dict[str, Any]):
    def exception_callback(helper: ExceptionCallbackHelper) -> None:
        assert not helper.create_issue
        helper.issue_fingerprint_source = 'custom fingerprint source'
        assert helper.issue_fingerprint_source == 'custom fingerprint source'
        assert helper.create_issue

    config_kwargs['advanced'].exception_callback = exception_callback
    logfire.configure(**config_kwargs)

    try:
        raise ValueError('test')
    except ValueError:
        logfire.notice('caught error', _exc_info=True)

    [span] = exporter.exported_spans
    assert span.attributes
    assert span.attributes[ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY] == snapshot(
        '88555bd8bc2401ab2887ac1f1286642f98322a580cfe30dd6ad067fffd4a01c9'
    )

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'caught error',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_exceptions.py',
                    'code.function': 'test_set_fingerprint',
                    'code.lineno': 123,
                    'logfire.msg_template': 'caught error',
                    'logfire.msg': 'caught error',
                    'logfire.span_type': 'log',
                    'logfire.level_num': 10,
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'ValueError',
                            'exception.message': 'test',
                            'exception.stacktrace': 'ValueError: test',
                            'exception.escaped': 'False',
                        },
                    }
                ],
            }
        ]
    )


def test_no_record_exception(exporter: TestExporter, config_kwargs: dict[str, Any]):
    def exception_callback(helper: ExceptionCallbackHelper) -> None:
        assert helper.create_issue
        helper.no_record_exception()
        assert not helper.create_issue
        with pytest.raises(ValueError):
            helper.create_issue = True
        with pytest.raises(ValueError):
            helper.issue_fingerprint_source = 'custom fingerprint source'
        assert not helper.create_issue

    config_kwargs['advanced'].exception_callback = exception_callback
    logfire.configure(**config_kwargs)

    with pytest.raises(ValueError):
        with logfire.span('span'):
            raise ValueError('test')

    (_pending, span) = exporter.exported_spans
    assert span.attributes
    assert ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY not in span.attributes

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_exceptions.py',
                    'code.function': 'test_no_record_exception',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                },
            }
        ]
    )


def test_record_exception_directly(exporter: TestExporter, config_kwargs: dict[str, Any]):
    def exception_callback(helper: ExceptionCallbackHelper) -> None:
        assert helper.level_is_unset
        assert helper.create_issue

    config_kwargs['advanced'].exception_callback = exception_callback
    logfire.configure(**config_kwargs)

    with logfire.span('span') as span:
        try:
            raise ValueError('test')
        except ValueError as e:
            span.record_exception(e)

    (_pending, span) = exporter.exported_spans
    assert span.attributes

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_exceptions.py',
                    'code.function': 'test_record_exception_directly',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'span',
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'ValueError',
                            'exception.message': 'test',
                            'exception.stacktrace': 'ValueError: test',
                            'exception.escaped': 'False',
                        },
                    }
                ],
            }
        ]
    )


@pytest.mark.skipif(sys.version_info < (3, 11), reason='co_positions traceback formatting was added in Python 3.11')
def test_span_records_exception_when_traceback_formatting_fails(exporter: TestExporter) -> None:
    """Regression test for CPython traceback failures from malformed bytecode position metadata."""

    def raise_from_code_with_truncated_positions() -> None:
        raise ValueError('test error')

    bad_code = raise_from_code_with_truncated_positions.__code__.replace(co_linetable=b'')
    bad_function = types.FunctionType(bad_code, globals())

    with pytest.raises(ValueError, match='test error'), logfire.span('span with malformed exception traceback'):
        bad_function()

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'span with malformed exception traceback',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_exceptions.py',
                    'code.function': 'test_span_records_exception_when_traceback_formatting_fails',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span with malformed exception traceback',
                    'logfire.msg': 'span with malformed exception traceback',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'ValueError',
                            'exception.message': 'test error',
                            'exception.stacktrace': (
                                'Formatting stacktrace failed: RuntimeError: generator raised StopIteration'
                            ),
                            'exception.escaped': 'True',
                        },
                    }
                ],
            }
        ]
    )


def test_nonrecording_span(exporter: TestExporter, config_kwargs: dict[str, Any]):
    config_kwargs['sampling'] = logfire.SamplingOptions(head=0)
    logfire.configure(**config_kwargs)

    with pytest.raises(ValueError):
        with logfire.span('span') as span:
            try:
                raise ValueError('test')
            except ValueError as e:
                span.record_exception(e)
                logfire.exception('span exception')
                raise

    assert exporter.exported_spans_as_dict() == snapshot([])


def test_span_records_exception_whose_str_raises(exporter: TestExporter, config_kwargs: dict[str, Any]) -> None:
    """An exception whose `__str__` raises must still be recorded on the span, not abort the recording."""

    class BadStr(Exception):
        def __str__(self) -> str:
            raise RuntimeError('str boom')

    logfire.configure(**config_kwargs)

    with pytest.raises(BadStr), logfire.span('foo'):
        raise BadStr('details')

    (_pending, span) = exporter.exported_spans
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == 'BadStr: <exception str() failed>'
    assert span.attributes is not None
    assert ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY in span.attributes
    [event] = span.events
    assert event.name == 'exception'
    assert event.attributes is not None
    assert event.attributes['exception.type'] == f'{BadStr.__module__}.{BadStr.__qualname__}'
    assert event.attributes['exception.message'] == '<exception str() failed>'
    assert event.attributes['exception.escaped'] == 'True'
    stacktrace = event.attributes['exception.stacktrace']
    assert isinstance(stacktrace, str)
    assert '<exception str() failed>' in stacktrace


def test_log_with_exception_whose_str_raises(exporter: TestExporter, config_kwargs: dict[str, Any]) -> None:
    """`logfire.exception()` must still export the log record when `str(exception)` raises.

    The status description used to be built with an f-string calling `str(exception)`,
    which aborted `Logfire.log` before the span was ended, so the whole record was lost.
    """

    class BadStr(Exception):
        def __str__(self) -> str:
            raise RuntimeError('str boom')

    logfire.configure(**config_kwargs)

    try:
        raise BadStr('details')
    except BadStr:
        logfire.exception('caught it')

    (span,) = exporter.exported_spans
    assert span.name == 'caught it'
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == 'BadStr: <exception str() failed>'
    [event] = span.events
    assert event.attributes is not None
    assert event.attributes['exception.message'] == '<exception str() failed>'


def test_exception_with_metaclass_that_rejects_name(exporter: TestExporter, config_kwargs: dict[str, Any]) -> None:
    """Reading the class name can raise as well, so the recorder must not depend on it."""

    class NoNameMeta(type):
        @property
        def __name__(cls) -> str:  # pyright: ignore[reportIncompatibleVariableOverride]
            raise RuntimeError('no name')

    class NoName(Exception, metaclass=NoNameMeta):
        def __str__(self) -> str:
            raise RuntimeError('str boom')

    logfire.configure(**config_kwargs)

    try:
        raise NoName('details')
    except NoName:
        logfire.exception('caught it')

    (span,) = exporter.exported_spans
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == 'exception: <exception str() failed>'
    [event] = span.events
    assert event.attributes is not None
    assert event.attributes['exception.type'] == f'{NoName.__module__}.{NoName.__qualname__}'
