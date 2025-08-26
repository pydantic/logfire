import sys
from typing import Any

import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.constants import ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY
from logfire._internal.exporters.test import TestExporter
from logfire._internal.utils import canonicalize_exception_traceback, sha256_string
from logfire.types import ExceptionCallbackHelper


def test_canonicalize_exception_func():
    def foo():
        bar()

    def bar():
        raise ValueError

    def foo2():
        bar2()

    def bar2():
        raise TypeError

    try:
        foo()
    except Exception as e:
        e1 = e

    try:
        foo()
    except Exception as e:
        e1_b = e

    try:
        foo2()
    except Exception:
        try:
            # Intentionally trigger a NameError by referencing an undefined variable
            exec('undefined_variable')
        except Exception:
            try:
                raise ZeroDivisionError
            except Exception as e4:
                e5 = e4

    canonicalized = canonicalize_exception_traceback(e5)  # type: ignore
    assert canonicalized.replace(__file__, '__file__') == snapshot("""\

builtins.ZeroDivisionError
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   raise ZeroDivisionError

__context__:

builtins.NameError
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   exec('undefined_variable')
tests.test_canonicalize_exception.<module>
   \n\

__context__:

builtins.TypeError
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   foo2()
tests.test_canonicalize_exception.foo2
   bar2()
tests.test_canonicalize_exception.bar2
   raise TypeError\
""")

    if sys.version_info < (3, 11):
        return

    try:
        raise BaseExceptionGroup('group', [e1, e1_b, e5])  # type: ignore  # noqa
    except BaseExceptionGroup as group:  # noqa
        try:
            raise Exception from group
        except Exception as e6:
            assert canonicalize_exception_traceback(e6).replace(__file__, '__file__') == snapshot("""\

builtins.Exception
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   raise Exception from group

__cause__:

builtins.ExceptionGroup
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   raise BaseExceptionGroup('group', [e1, e1_b, e5])  # type: ignore  # noqa

<ExceptionGroup>

builtins.ValueError
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   foo()
tests.test_canonicalize_exception.foo
   bar()
tests.test_canonicalize_exception.bar
   raise ValueError

builtins.ZeroDivisionError
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   raise ZeroDivisionError

__context__:

builtins.NameError
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   exec('undefined_variable')
tests.test_canonicalize_exception.<module>
   \n\

__context__:

builtins.TypeError
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   foo2()
tests.test_canonicalize_exception.foo2
   bar2()
tests.test_canonicalize_exception.bar2
   raise TypeError

</ExceptionGroup>
""")


def test_canonicalize_repeated_frame_exception():
    def foo(n: int):
        if n == 0:
            raise ValueError
        bar(n)

    def bar(n: int):
        foo(n - 1)

    try:
        foo(3)
    except Exception as e:
        canonicalized = canonicalize_exception_traceback(e)
        assert canonicalized.replace(__file__, '__file__') == snapshot("""\

builtins.ValueError
----
tests.test_canonicalize_exception.test_canonicalize_repeated_frame_exception
   foo(3)
tests.test_canonicalize_exception.foo
   bar(n)
tests.test_canonicalize_exception.bar
   foo(n - 1)
tests.test_canonicalize_exception.foo
   raise ValueError\
""")


def test_sha256_string():
    assert sha256_string('test') == snapshot('9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08')


def test_fingerprint_attribute(exporter: TestExporter):
    with pytest.raises(ValueError):
        with logfire.span('foo'):
            raise ValueError('test')

    (_pending, span) = exporter.exported_spans
    assert span.attributes
    assert span.attributes[ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY] == snapshot(
        '3ca86c8642e26597ed1f2485859197fd294e17719e31b302b55246dab493ce83'
    )


def test_cyclic_exception_cause():
    try:
        try:
            raise ValueError('test')
        except Exception as e:
            raise e from e
    except Exception as e2:
        assert canonicalize_exception_traceback(e2) == snapshot("""\

builtins.ValueError
----
tests.test_canonicalize_exception.test_cyclic_exception_cause
   raise e from e
tests.test_canonicalize_exception.test_cyclic_exception_cause
   raise ValueError('test')

__cause__:

builtins.ValueError
----
tests.test_canonicalize_exception.test_cyclic_exception_cause
   raise e from e
tests.test_canonicalize_exception.test_cyclic_exception_cause
   raise ValueError('test')

<repeated exception>\
""")


@pytest.mark.skipif(sys.version_info < (3, 11), reason='ExceptionGroup is not available in Python < 3.11')
def test_cyclic_exception_group():
    try:
        raise ExceptionGroup('group', [ValueError('test')])  # noqa
    except ExceptionGroup as group:  # noqa
        try:
            raise group.exceptions[0]
        except Exception as e:
            assert canonicalize_exception_traceback(e) == snapshot("""\

builtins.ValueError
----
tests.test_canonicalize_exception.test_cyclic_exception_group
   raise group.exceptions[0]

__context__:

builtins.ExceptionGroup
----
tests.test_canonicalize_exception.test_cyclic_exception_group
   raise ExceptionGroup('group', [ValueError('test')])  # noqa

<ExceptionGroup>

builtins.ValueError
----
tests.test_canonicalize_exception.test_cyclic_exception_group
   raise group.exceptions[0]

<repeated exception>

</ExceptionGroup>
""")


def test_exception_callback_set_level(exporter: TestExporter, config_kwargs: dict[str, Any]):
    def exception_callback(helper: ExceptionCallbackHelper) -> None:
        assert helper.level.name == 'error'
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
