import sys

from inline_snapshot import snapshot

from logfire._internal.utils import canonicalize_exception, sha256_string


def test_canonicalize_exception():
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
__file__:test_canonicalize_exception
    raise ZeroDivisionError

__context__:

builtins.NameError
----
__file__:test_canonicalize_exception
    exec('qiwoue')
<string>:<module>
    \n\

__context__:

builtins.TypeError
----
__file__:test_canonicalize_exception
    foo2()
__file__:foo2
    bar2()
__file__:bar2
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
__file__:test_canonicalize_exception
    raise Exception

__context__:

builtins.ExceptionGroup
----
__file__:test_canonicalize_exception
    raise BaseExceptionGroup('group', [e1, e1_b, e5])  # type: ignore

<ExceptionGroup>

builtins.ValueError
----
__file__:test_canonicalize_exception
    foo()
__file__:foo
    bar()
__file__:bar
    raise ValueError

builtins.ZeroDivisionError
----
__file__:test_canonicalize_exception
    raise ZeroDivisionError

__context__:

builtins.NameError
----
__file__:test_canonicalize_exception
    exec('qiwoue')
<string>:<module>
    \n\

__context__:

builtins.TypeError
----
__file__:test_canonicalize_exception
    foo2()
__file__:foo2
    bar2()
__file__:bar2
    raise TypeError

</ExceptionGroup>
""")


def test_sha256_string():
    assert sha256_string('test') == snapshot('9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08')
