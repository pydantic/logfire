from tests.import_used_for_tests.internal_error_handling.internal_logfire_code_example import (
    outer2,
    using_context_manager,
    using_decorator,
    using_try_except,
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
    outer2(using_decorator)
    outer2(using_context_manager)
    outer2(using_try_except)
