import math
from contextlib import ExitStack

from logfire import Logfire, install_automatic_instrumentation, uninstall_automatic_instrumentation
from logfire.testing import TestExporter

from .module_used_for_tests import wrap


class Foo:
    def bar(self) -> None:
        return None


def foo(x: int) -> float:
    d: dict[str, int] = {}
    d.get('a', None)  # access a method on a built in type
    f = Foo()
    f.bar()  # access a method on a user defined type
    xs = [x for x in range(x)]  # comprehension
    x = sum(xs)  # call a builtin function
    return math.sin(x)  # call a python function from a builtin module


def test_auto_instrumentation_no_filter(logfire: Logfire, exporter: TestExporter) -> None:
    with ExitStack() as stack:
        stack.callback(uninstall_automatic_instrumentation)

        install_automatic_instrumentation(logfire=logfire)

        wrap(foo, 1)

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'function wrap() called',
            'context': {'trace_id': 0, 'span_id': 0, 'is_remote': False},
            'parent': {'trace_id': 0, 'span_id': 1, 'is_remote': False},
            'start_time': 2,
            'end_time': 2,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'function {func_name}() called',
                'code.function': 'wrap',
                'code.lineno': 123,
                'code.filepath': 'test_auto_instrumentation.py',
                'code.namespace': 'tests.module_used_for_tests',
                'func_name': 'wrap',
                'span_name': 'tests.module_used_for_tests.wrap',
            },
        },
        {
            'name': 'tests.module_used_for_tests.wrap',
            'context': {'trace_id': 0, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 2,
            'end_time': 3,
            'attributes': {'logfire.log_type': 'real_span'},
        },
        {
            'name': 'function foo() called',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'start_time': 6,
            'end_time': 6,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'function {func_name}() called',
                'code.function': 'foo',
                'code.lineno': 123,
                'code.filepath': 'module_used_for_tests.py',
                'code.namespace': 'tests.test_auto_instrumentation',
                'func_name': 'foo',
                'span_name': 'tests.test_auto_instrumentation.foo',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': None,
            'start_time': 6,
            'end_time': 7,
            'attributes': {'logfire.log_type': 'real_span'},
        },
        {
            'name': 'function Foo.bar() called',
            'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
            'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
            'start_time': 10,
            'end_time': 10,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'function {func_name}() called',
                'code.function': 'Foo.bar',
                'code.lineno': 123,
                'code.filepath': 'test_auto_instrumentation.py',
                'code.namespace': 'tests.test_auto_instrumentation',
                'func_name': 'Foo.bar',
                'span_name': 'tests.test_auto_instrumentation.Foo.bar',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.Foo.bar',
            'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
            'parent': None,
            'start_time': 10,
            'end_time': 11,
            'attributes': {'logfire.log_type': 'real_span'},
        },
        {
            'name': 'function foo.<locals>.<listcomp>() called',
            'context': {'trace_id': 3, 'span_id': 6, 'is_remote': False},
            'parent': {'trace_id': 3, 'span_id': 7, 'is_remote': False},
            'start_time': 14,
            'end_time': 14,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'function {func_name}() called',
                'code.function': 'foo.<locals>.<listcomp>',
                'code.lineno': 123,
                'code.filepath': 'test_auto_instrumentation.py',
                'code.namespace': 'tests.test_auto_instrumentation',
                'func_name': 'foo.<locals>.<listcomp>',
                'span_name': 'tests.test_auto_instrumentation.foo.<locals>.<listcomp>',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo.<locals>.<listcomp>',
            'context': {'trace_id': 3, 'span_id': 7, 'is_remote': False},
            'parent': None,
            'start_time': 14,
            'end_time': 15,
            'attributes': {'logfire.log_type': 'real_span'},
        },
    ]


def test_auto_instrumentation_filter_modules(logfire: Logfire, exporter: TestExporter) -> None:
    with ExitStack() as stack:
        stack.callback(uninstall_automatic_instrumentation)

        install_automatic_instrumentation(modules=[__name__], logfire=logfire)

        wrap(foo, 1)

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'function foo() called',
            'context': {'trace_id': 0, 'span_id': 0, 'is_remote': False},
            'parent': {'trace_id': 0, 'span_id': 1, 'is_remote': False},
            'start_time': 2,
            'end_time': 2,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'function {func_name}() called',
                'code.function': 'foo',
                'code.lineno': 123,
                'code.filepath': 'module_used_for_tests.py',
                'code.namespace': 'tests.test_auto_instrumentation',
                'func_name': 'foo',
                'span_name': 'tests.test_auto_instrumentation.foo',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo',
            'context': {'trace_id': 0, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 2,
            'end_time': 3,
            'attributes': {'logfire.log_type': 'real_span'},
        },
        {
            'name': 'function Foo.bar() called',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'start_time': 6,
            'end_time': 6,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'function {func_name}() called',
                'code.function': 'Foo.bar',
                'code.lineno': 123,
                'code.filepath': 'test_auto_instrumentation.py',
                'code.namespace': 'tests.test_auto_instrumentation',
                'func_name': 'Foo.bar',
                'span_name': 'tests.test_auto_instrumentation.Foo.bar',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.Foo.bar',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': None,
            'start_time': 6,
            'end_time': 7,
            'attributes': {'logfire.log_type': 'real_span'},
        },
        {
            'name': 'function foo.<locals>.<listcomp>() called',
            'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
            'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
            'start_time': 10,
            'end_time': 10,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'function {func_name}() called',
                'code.function': 'foo.<locals>.<listcomp>',
                'code.lineno': 123,
                'code.filepath': 'test_auto_instrumentation.py',
                'code.namespace': 'tests.test_auto_instrumentation',
                'func_name': 'foo.<locals>.<listcomp>',
                'span_name': 'tests.test_auto_instrumentation.foo.<locals>.<listcomp>',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo.<locals>.<listcomp>',
            'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
            'parent': None,
            'start_time': 10,
            'end_time': 11,
            'attributes': {'logfire.log_type': 'real_span'},
        },
    ]
