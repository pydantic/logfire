import math
import sys
from contextlib import ExitStack

from dirty_equals import IsStr

from logfire import install_automatic_instrumentation, uninstall_automatic_instrumentation
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


def test_auto_instrumentation_no_filter(exporter: TestExporter) -> None:
    with ExitStack() as stack:
        stack.callback(uninstall_automatic_instrumentation)

        install_automatic_instrumentation()

        wrap(foo, 1)

    expected_spans = [
        {
            'name': 'tests.module_used_for_tests.wrap (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': 'wrap',
                'code.namespace': 'tests.module_used_for_tests',
                'function_name': 'wrap',
                'logfire.msg_template': 'function {function_name}() called',
                'logfire.msg': 'function wrap() called',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'tests.module_used_for_tests.wrap',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': 'wrap',
                'code.namespace': 'tests.module_used_for_tests',
                'function_name': 'wrap',
                'logfire.msg_template': 'function {function_name}() called',
                'logfire.msg': 'function wrap() called',
                'logfire.span_type': 'span',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo (start)',
            'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
            'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
            'start_time': 3000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': 'module_used_for_tests.py',
                'code.lineno': 123,
                'code.function': 'foo',
                'code.namespace': 'tests.test_auto_instrumentation',
                'function_name': 'foo',
                'logfire.msg_template': 'function {function_name}() called',
                'logfire.msg': 'function foo() called',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo',
            'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
            'parent': None,
            'start_time': 3000000000,
            'end_time': 4000000000,
            'attributes': {
                'code.filepath': 'module_used_for_tests.py',
                'code.lineno': 123,
                'code.function': 'foo',
                'code.namespace': 'tests.test_auto_instrumentation',
                'function_name': 'foo',
                'logfire.msg_template': 'function {function_name}() called',
                'logfire.msg': 'function foo() called',
                'logfire.span_type': 'span',
            },
        },
        {
            'name': IsStr(regex=r'tests.test_auto_instrumentation(\.Foo)?.bar \(start\)'),
            'context': {'trace_id': 3, 'span_id': 6, 'is_remote': False},
            'parent': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
            'start_time': 5000000000,
            'end_time': 5000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': IsStr(regex=r'(Foo\.)?bar'),
                'code.namespace': 'tests.test_auto_instrumentation',
                'function_name': IsStr(regex=r'(Foo\.)?bar'),
                'logfire.msg_template': 'function {function_name}() called',
                'logfire.msg': IsStr(regex=r'function (Foo\.)?bar\(\) called'),
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': IsStr(regex=r'tests.test_auto_instrumentation.(Foo\.)?bar'),
            'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
            'parent': None,
            'start_time': 5000000000,
            'end_time': 6000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': IsStr(regex=r'(Foo\.)?bar'),
                'code.namespace': 'tests.test_auto_instrumentation',
                'function_name': IsStr(regex=r'(Foo\.)?bar'),
                'logfire.msg_template': 'function {function_name}() called',
                'logfire.msg': IsStr(regex=r'function (Foo\.)?bar\(\) called'),
                'logfire.span_type': 'span',
            },
        },
    ]
    if sys.version_info < (3, 12):
        expected_spans += [
            {
                'name': IsStr(regex=r'tests.test_auto_instrumentation.(foo.\<locals\>.)?\<listcomp\> \(start\)'),
                'context': {'trace_id': 4, 'span_id': 8, 'is_remote': False},
                'parent': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
                'start_time': 7000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'test_auto_instrumentation.py',
                    'code.lineno': 123,
                    'code.function': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                    'code.namespace': 'tests.test_auto_instrumentation',
                    'function_name': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                    'logfire.msg_template': 'function {function_name}() called',
                    'logfire.msg': IsStr(regex=r'function (foo.\<locals\>.)?\<listcomp\>\(\) called'),
                    'logfire.span_type': 'start_span',
                    'logfire.start_parent_id': '0',
                },
            },
            {
                'name': IsStr(regex=r'tests.test_auto_instrumentation.(foo.\<locals\>.)?\<listcomp\>'),
                'context': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
                'parent': None,
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_auto_instrumentation.py',
                    'code.lineno': 123,
                    'code.function': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                    'code.namespace': 'tests.test_auto_instrumentation',
                    'function_name': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                    'logfire.msg_template': 'function {function_name}() called',
                    'logfire.msg': IsStr(regex=r'function (foo.\<locals\>.)?\<listcomp\>\(\) called'),
                    'logfire.span_type': 'span',
                },
            },
        ]

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == expected_spans


def test_auto_instrumentation_filter_modules(exporter: TestExporter) -> None:
    with ExitStack() as stack:
        stack.callback(uninstall_automatic_instrumentation)

        install_automatic_instrumentation(modules=[__name__])

        wrap(foo, 1)

    expected_spans = [
        {
            'name': 'tests.test_auto_instrumentation.foo (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'module_used_for_tests.py',
                'code.lineno': 123,
                'code.function': 'foo',
                'code.namespace': 'tests.test_auto_instrumentation',
                'function_name': 'foo',
                'logfire.msg_template': 'function {function_name}() called',
                'logfire.msg': 'function foo() called',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': 'module_used_for_tests.py',
                'code.lineno': 123,
                'code.function': 'foo',
                'code.namespace': 'tests.test_auto_instrumentation',
                'function_name': 'foo',
                'logfire.msg_template': 'function {function_name}() called',
                'logfire.msg': 'function foo() called',
                'logfire.span_type': 'span',
            },
        },
        {
            'name': IsStr(regex=r'tests.test_auto_instrumentation.(Foo.)?bar \(start\)'),
            'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
            'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
            'start_time': 3000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': IsStr(regex=r'(Foo.)?bar'),
                'code.namespace': 'tests.test_auto_instrumentation',
                'function_name': IsStr(regex=r'(Foo.)?bar'),
                'logfire.msg_template': 'function {function_name}() called',
                'logfire.msg': IsStr(regex=r'function (Foo.)?bar\(\) called'),
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': IsStr(regex=r'tests.test_auto_instrumentation.(Foo.)?bar'),
            'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
            'parent': None,
            'start_time': 3000000000,
            'end_time': 4000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': IsStr(regex=r'(Foo.)?bar'),
                'code.namespace': 'tests.test_auto_instrumentation',
                'function_name': IsStr(regex=r'(Foo.)?bar'),
                'logfire.msg_template': 'function {function_name}() called',
                'logfire.msg': IsStr(regex=r'function (Foo.)?bar\(\) called'),
                'logfire.span_type': 'span',
            },
        },
    ]
    if sys.version_info < (3, 12):
        expected_spans += [
            {
                'name': IsStr(regex=r'tests.test_auto_instrumentation.(foo.\<locals\>.)?\<listcomp\> \(start\)'),
                'context': {'trace_id': 3, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_auto_instrumentation.py',
                    'code.lineno': 123,
                    'code.function': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                    'code.namespace': 'tests.test_auto_instrumentation',
                    'function_name': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                    'logfire.msg_template': 'function {function_name}() called',
                    'logfire.msg': IsStr(regex=r'function (foo.\<locals\>.)?\<listcomp\>\(\) called'),
                    'logfire.span_type': 'start_span',
                    'logfire.start_parent_id': '0',
                },
            },
            {
                'name': IsStr(regex=r'tests.test_auto_instrumentation.(foo.\<locals\>.)?\<listcomp\>'),
                'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_auto_instrumentation.py',
                    'code.lineno': 123,
                    'code.function': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                    'code.namespace': 'tests.test_auto_instrumentation',
                    'function_name': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                    'logfire.msg_template': 'function {function_name}() called',
                    'logfire.msg': IsStr(regex=r'function (foo.\<locals\>.)?\<listcomp\>\(\) called'),
                    'logfire.span_type': 'span',
                },
            },
        ]
    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == expected_spans
