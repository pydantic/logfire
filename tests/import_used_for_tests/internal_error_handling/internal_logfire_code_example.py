from typing import Any

from logfire._internal.utils import handle_internal_errors, log_internal_error


def inner1():
    raise ValueError('inner1')


def inner2():
    inner1()


@handle_internal_errors
def using_decorator():
    inner2()


def using_context_manager():
    with handle_internal_errors:
        inner2()


def using_try_except():
    try:
        inner2()
    except Exception:
        log_internal_error()


def outer1(func: Any):
    func()


def outer2(func: Any):
    outer1(func)
