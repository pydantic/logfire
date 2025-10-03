from typing import Any

import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.constants import ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY
from logfire._internal.exporters.test import TestExporter
from logfire._internal.utils import canonicalize_exception_traceback
from logfire.types import ExceptionCallbackHelper


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
