from typing import Any

from logfire._internal.utils import handle_internal_errors, log_internal_error


def _inner1():
    raise ValueError('inner1')


def _inner2():
    _inner1()


@handle_internal_errors()
def _using_decorator():  # type: ignore
    _inner2()


def _using_context_manager():  # type: ignore
    with handle_internal_errors():
        _inner2()


def _using_try_except():  # type: ignore
    try:
        _inner2()
    except Exception:
        log_internal_error()


def _outer1(func: Any):
    func()


def _outer2(func: Any):  # type: ignore
    _outer1(func)
