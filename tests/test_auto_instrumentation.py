import math
from contextlib import ExitStack

from logfire import Logfire, install_automatic_instrumentation, uninstall_automatic_instrumentation

from .conftest import TestExporter
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

    logfire._config.provider.force_flush()  # type: ignore

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'function wrap() called',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1,
            'end_time': 1,
            'attributes': {
                'code.namespace': 'tests.module_used_for_tests',
                'code.function': 'wrap',
                'code.lineno': 31,
                'code.filepath': 'src/packages/logfire/tests/test_auto_instrumentation.py',
                'logfire.log_type': 'start_span',
            },
        },
        {
            'name': 'tests.module_used_for_tests.wrap',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1,
            'end_time': 2,
            'attributes': {'logfire.log_type': 'real_span'},
        },
        {
            'name': 'function foo() called',
            'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
            'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
            'start_time': 3,
            'end_time': 3,
            'attributes': {
                'code.namespace': 'tests.test_auto_instrumentation',
                'code.function': 'foo',
                'code.lineno': 12,
                'code.filepath': 'src/packages/logfire/tests/module_used_for_tests.py',
                'logfire.log_type': 'start_span',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo',
            'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
            'parent': None,
            'start_time': 3,
            'end_time': 4,
            'attributes': {'logfire.log_type': 'real_span'},
        },
        {
            'name': 'function Foo.bar() called',
            'context': {'trace_id': 3, 'span_id': 6, 'is_remote': False},
            'parent': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
            'start_time': 5,
            'end_time': 5,
            'attributes': {
                'code.namespace': 'tests.test_auto_instrumentation',
                'code.function': 'Foo.bar',
                'code.lineno': 19,
                'code.filepath': 'src/packages/logfire/tests/test_auto_instrumentation.py',
                'logfire.log_type': 'start_span',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.Foo.bar',
            'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
            'parent': None,
            'start_time': 5,
            'end_time': 6,
            'attributes': {'logfire.log_type': 'real_span'},
        },
        {
            'name': 'function foo.<locals>.<listcomp>() called',
            'context': {'trace_id': 4, 'span_id': 8, 'is_remote': False},
            'parent': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
            'start_time': 7,
            'end_time': 7,
            'attributes': {
                'code.namespace': 'tests.test_auto_instrumentation',
                'code.function': 'foo.<locals>.<listcomp>',
                'code.lineno': 20,
                'code.filepath': 'src/packages/logfire/tests/test_auto_instrumentation.py',
                'logfire.log_type': 'start_span',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo.<locals>.<listcomp>',
            'context': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
            'parent': None,
            'start_time': 7,
            'end_time': 8,
            'attributes': {'logfire.log_type': 'real_span'},
        },
    ]


def test_auto_instrumentation_filter_modules(logfire: Logfire, exporter: TestExporter) -> None:
    with ExitStack() as stack:
        stack.callback(uninstall_automatic_instrumentation)

        install_automatic_instrumentation(modules=[__name__], logfire=logfire)

        wrap(foo, 1)

    logfire._config.provider.force_flush()  # type: ignore

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'function foo() called',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1,
            'end_time': 1,
            'attributes': {
                'code.namespace': 'tests.test_auto_instrumentation',
                'code.function': 'foo',
                'code.lineno': 12,
                'code.filepath': 'src/packages/logfire/tests/module_used_for_tests.py',
                'logfire.log_type': 'start_span',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1,
            'end_time': 2,
            'attributes': {'logfire.log_type': 'real_span'},
        },
        {
            'name': 'function Foo.bar() called',
            'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
            'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
            'start_time': 3,
            'end_time': 3,
            'attributes': {
                'code.namespace': 'tests.test_auto_instrumentation',
                'code.function': 'Foo.bar',
                'code.lineno': 19,
                'code.filepath': 'src/packages/logfire/tests/test_auto_instrumentation.py',
                'logfire.log_type': 'start_span',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.Foo.bar',
            'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
            'parent': None,
            'start_time': 3,
            'end_time': 4,
            'attributes': {'logfire.log_type': 'real_span'},
        },
        {
            'name': 'function foo.<locals>.<listcomp>() called',
            'context': {'trace_id': 3, 'span_id': 6, 'is_remote': False},
            'parent': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
            'start_time': 5,
            'end_time': 5,
            'attributes': {
                'code.namespace': 'tests.test_auto_instrumentation',
                'code.function': 'foo.<locals>.<listcomp>',
                'code.lineno': 20,
                'code.filepath': 'src/packages/logfire/tests/test_auto_instrumentation.py',
                'logfire.log_type': 'start_span',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo.<locals>.<listcomp>',
            'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
            'parent': None,
            'start_time': 5,
            'end_time': 6,
            'attributes': {'logfire.log_type': 'real_span'},
        },
    ]
