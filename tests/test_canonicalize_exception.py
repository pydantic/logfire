import sys

import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.exporters.test import TestExporter
from logfire._internal.utils import canonicalize_exception, sha256_string


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
            exec('qiwoue')
        except Exception:
            try:
                raise ZeroDivisionError
            except Exception as e4:
                e5 = e4

    canonicalized = canonicalize_exception(e5)  # type: ignore
    assert canonicalized.replace(__file__, '__file__') == snapshot("""\

builtins.ZeroDivisionError
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   raise ZeroDivisionError

__context__:

builtins.NameError
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   exec('qiwoue')
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
    except BaseExceptionGroup:  # noqa
        try:
            raise Exception
        except Exception as e6:
            assert canonicalize_exception(e6).replace(__file__, '__file__') == snapshot("""\

builtins.Exception
----
tests.test_canonicalize_exception.test_canonicalize_exception_func
   raise Exception

__context__:

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
   exec('qiwoue')
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
        canonicalized = canonicalize_exception(e)
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
    assert span.attributes['logfire.exception.fingerprint'] == snapshot(
        '3ca86c8642e26597ed1f2485859197fd294e17719e31b302b55246dab493ce83'
    )
