import sys

import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.constants import ATTRIBUTES_EXCEPTION_FINGERPRINT_KEY
from logfire._internal.exporters.test import TestExporter
from logfire._internal.utils import canonicalize_exception_traceback, sha256_string


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
