from logfire._internal.internal_error_tb_sample import (
    _outer2,  # type: ignore
    _using_context_manager,  # type: ignore
    _using_decorator,  # type: ignore
    _using_try_except,  # type: ignore
)


def user1():
    user2()


def user2():
    user3()


def user3():
    user4()


def user4():
    user5()


def user5():
    user6()


def user6():
    _outer2(_using_decorator)
    _outer2(_using_context_manager)
    _outer2(_using_try_except)
