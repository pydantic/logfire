import re

import pytest
import requests
import requests_mock
from inline_snapshot import snapshot

import logfire
from logfire._internal.utils import UnexpectedResponse, handle_internal_errors
from tests.import_used_for_tests.internal_error_handling import internal_logfire_code_example, user_code_example


def test_raise_for_status() -> None:
    with requests_mock.Mocker() as m:
        m.get('https://test.com', text='this is the body', status_code=503)
        r = requests.get('https://test.com')

    with pytest.raises(UnexpectedResponse) as exc_info:
        UnexpectedResponse.raise_for_status(r)
    s = str(exc_info.value)
    assert s.startswith('Unexpected response 503')
    assert 'body: this is the body' in s


def test_reraise_internal_exception():
    with pytest.raises(ZeroDivisionError):
        with handle_internal_errors:
            str(1 / 0)


def test_internal_exception_tb(caplog: pytest.LogCaptureFixture):
    # Pretend that `internal_logfire_code_example` is a module within logfire,
    # so all frames from it should be included.
    logfire.add_non_user_code_prefix(internal_logfire_code_example.__file__)

    user_code_example.user1()

    tracebacks = [
        re.sub(
            # Remove lines with ~ and ^ pointers (and whitespace) only
            r'\n[ ~^]+\n',
            '\n',
            r.exc_text.replace(  # type: ignore
                user_code_example.__file__,
                'user_code_example.py',
            ).replace(
                internal_logfire_code_example.__file__,
                'internal_logfire_code_example.py',
            ),
        )
        for r in caplog.records
    ]

    # Important notes about these tracebacks:
    # - They should look very similar to each other, regardless of how log_internal_error was called.
    # - They should include all frames from internal_logfire_code_example.py.
    # - They should include exactly 3 frames from user_code_example.py.
    # - They should look seamless, with each frame pointing to the next one.
    # - There should be no sign of logfire's internal error handling code.
    # - The two files should be isolated and stable so that the exact traceback contents can be asserted.
    assert tracebacks == snapshot(
        [
            """\
Traceback (most recent call last):
  File "user_code_example.py", line 22, in user4
    user5()
  File "user_code_example.py", line 26, in user5
    user6()
  File "user_code_example.py", line 30, in user6
    outer2(using_decorator)
  File "internal_logfire_code_example.py", line 36, in outer2
    outer1(func)
  File "internal_logfire_code_example.py", line 32, in outer1
    func()
  File "internal_logfire_code_example.py", line 16, in using_decorator
    inner2()
  File "internal_logfire_code_example.py", line 11, in inner2
    inner1()
  File "internal_logfire_code_example.py", line 7, in inner1
    raise ValueError('inner1')
ValueError: inner1\
""",
            """\
Traceback (most recent call last):
  File "user_code_example.py", line 22, in user4
    user5()
  File "user_code_example.py", line 26, in user5
    user6()
  File "user_code_example.py", line 31, in user6
    outer2(using_context_manager)
  File "internal_logfire_code_example.py", line 36, in outer2
    outer1(func)
  File "internal_logfire_code_example.py", line 32, in outer1
    func()
  File "internal_logfire_code_example.py", line 21, in using_context_manager
    inner2()
  File "internal_logfire_code_example.py", line 11, in inner2
    inner1()
  File "internal_logfire_code_example.py", line 7, in inner1
    raise ValueError('inner1')
ValueError: inner1\
""",
            """\
Traceback (most recent call last):
  File "user_code_example.py", line 22, in user4
    user5()
  File "user_code_example.py", line 26, in user5
    user6()
  File "user_code_example.py", line 32, in user6
    outer2(using_try_except)
  File "internal_logfire_code_example.py", line 36, in outer2
    outer1(func)
  File "internal_logfire_code_example.py", line 32, in outer1
    func()
  File "internal_logfire_code_example.py", line 26, in using_try_except
    inner2()
  File "internal_logfire_code_example.py", line 11, in inner2
    inner1()
  File "internal_logfire_code_example.py", line 7, in inner1
    raise ValueError('inner1')
ValueError: inner1\
""",
        ]
    )


def test_internal_error_base_exception():
    with pytest.raises(BaseException):
        with handle_internal_errors:
            raise BaseException('base exception')
