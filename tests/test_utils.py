import pytest
import requests
import requests_mock
from inline_snapshot import snapshot

from logfire._internal import internal_error_tb_sample
from logfire._internal.utils import UnexpectedResponse, handle_internal_errors
from tests.import_used_for_tests import handle_internal_error_example


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
        with handle_internal_errors():
            str(1 / 0)


def test_internal_exception_tb(caplog: pytest.LogCaptureFixture):
    handle_internal_error_example.user1()
    assert [
        r.exc_text.replace(  # type: ignore
            handle_internal_error_example.__file__,
            'handle_internal_error_example.py',
        ).replace(
            internal_error_tb_sample.__file__,
            'internal_error_tb_sample.py',
        )
        for r in caplog.records
    ] == snapshot(
        [
            """\
Traceback (most recent call last):
  File "handle_internal_error_example.py", line 22, in user4
    user5()
  File "handle_internal_error_example.py", line 26, in user5
    user6()
  File "handle_internal_error_example.py", line 30, in user6
    _outer2(_using_decorator)
  File "internal_error_tb_sample.py", line 36, in _outer2
    _outer1(func)
  File "internal_error_tb_sample.py", line 32, in _outer1
    func()
  File "internal_error_tb_sample.py", line 16, in _using_decorator
    _inner2()
  File "internal_error_tb_sample.py", line 11, in _inner2
    _inner1()
  File "internal_error_tb_sample.py", line 7, in _inner1
    raise ValueError('inner1')
ValueError: inner1\
""",
            """\
Traceback (most recent call last):
  File "handle_internal_error_example.py", line 22, in user4
    user5()
  File "handle_internal_error_example.py", line 26, in user5
    user6()
  File "handle_internal_error_example.py", line 31, in user6
    _outer2(_using_context_manager)
  File "internal_error_tb_sample.py", line 36, in _outer2
    _outer1(func)
  File "internal_error_tb_sample.py", line 32, in _outer1
    func()
  File "internal_error_tb_sample.py", line 21, in _using_context_manager
    _inner2()
  File "internal_error_tb_sample.py", line 11, in _inner2
    _inner1()
  File "internal_error_tb_sample.py", line 7, in _inner1
    raise ValueError('inner1')
ValueError: inner1\
""",
            """\
Traceback (most recent call last):
  File "handle_internal_error_example.py", line 22, in user4
    user5()
  File "handle_internal_error_example.py", line 26, in user5
    user6()
  File "handle_internal_error_example.py", line 32, in user6
    _outer2(_using_try_except)
  File "internal_error_tb_sample.py", line 36, in _outer2
    _outer1(func)
  File "internal_error_tb_sample.py", line 32, in _outer1
    func()
  File "internal_error_tb_sample.py", line 26, in _using_try_except
    _inner2()
  File "internal_error_tb_sample.py", line 11, in _inner2
    _inner1()
  File "internal_error_tb_sample.py", line 7, in _inner1
    raise ValueError('inner1')
ValueError: inner1\
""",
        ]
    )
