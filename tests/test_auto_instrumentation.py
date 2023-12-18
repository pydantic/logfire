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

    # On 3.12, list comprehensions do not generate a frame
    listcomp_offset = 2000000000
    if sys.version_info >= (3, 12):
        listcomp_offset = 0

    expected_spans = [
        {
            'name': 'tests.module_used_for_tests.wrap (pending)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': 'wrap',
                'code.namespace': 'tests.module_used_for_tests',
                'object': 'wrap',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call wrap',
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '0',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo (pending)',
            'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': 'module_used_for_tests.py',
                'code.lineno': 123,
                'code.function': 'foo',
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': 'foo',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call foo',
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '1',
            },
        },
        {
            'name': IsStr(regex=r'tests.test_auto_instrumentation(\.Foo)?.bar \(pending\)'),
            'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
            'start_time': 3000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': IsStr(regex=r'(Foo\.)?bar'),
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': IsStr(regex=r'(Foo\.)?bar'),
                'logfire.msg_template': 'call {object}',
                'logfire.msg': IsStr(regex=r'call (Foo\.)?bar'),
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '3',
            },
        },
        {
            'name': IsStr(regex=r'tests.test_auto_instrumentation.(Foo\.)?bar'),
            'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'start_time': 3000000000,
            'end_time': 4000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': IsStr(regex=r'(Foo\.)?bar'),
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': IsStr(regex=r'(Foo\.)?bar'),
                'logfire.msg_template': 'call {object}',
                'logfire.msg': IsStr(regex=r'call (Foo\.)?bar'),
                'logfire.span_type': 'span',
            },
        },
        *(
            (
                {
                    'name': IsStr(regex=r'tests.test_auto_instrumentation.(foo.\<locals\>.)?\<listcomp\> \(pending\)'),
                    'context': {'trace_id': 1, 'span_id': 8, 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                    'start_time': 5000000000,
                    'end_time': 5000000000,
                    'attributes': {
                        'code.filepath': 'test_auto_instrumentation.py',
                        'code.lineno': 123,
                        'code.function': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'code.namespace': 'tests.test_auto_instrumentation',
                        'object': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.msg_template': 'call {object}',
                        'logfire.msg': IsStr(regex=r'call (foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.span_type': 'pending_span',
                        'logfire.pending_parent_id': '3',
                    },
                },
                {
                    'name': IsStr(regex=r'tests.test_auto_instrumentation.(foo.\<locals\>.)?\<listcomp\>'),
                    'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                    'start_time': 5000000000,
                    'end_time': 6000000000,
                    'attributes': {
                        'code.filepath': 'test_auto_instrumentation.py',
                        'code.lineno': 123,
                        'code.function': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'code.namespace': 'tests.test_auto_instrumentation',
                        'object': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.msg_template': 'call {object}',
                        'logfire.msg': IsStr(regex=r'call (foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.span_type': 'span',
                    },
                },
            )
            if sys.version_info < (3, 12)
            else ()
        ),
        {
            'name': 'tests.test_auto_instrumentation.foo',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 5000000000 + listcomp_offset,
            'attributes': {
                'code.filepath': 'module_used_for_tests.py',
                'code.lineno': 123,
                'code.function': 'foo',
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': 'foo',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call foo',
                'logfire.span_type': 'span',
            },
        },
        {
            'name': 'tests.module_used_for_tests.wrap',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 6000000000 + listcomp_offset,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': 'wrap',
                'code.namespace': 'tests.module_used_for_tests',
                'object': 'wrap',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call wrap',
                'logfire.span_type': 'span',
            },
        },
    ]

    # insert_assert(exporter.exported_spans_as_dict(_include_pending_spans=True))
    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == expected_spans


def test_auto_instrumentation_filter_modules(exporter: TestExporter) -> None:
    with ExitStack() as stack:
        stack.callback(uninstall_automatic_instrumentation)

        install_automatic_instrumentation(modules=[__name__])

        wrap(foo, 1)

    # On 3.12, list comprehensions do not generate a frame
    listcomp_offset = 2000000000
    if sys.version_info >= (3, 12):
        listcomp_offset = 0

    expected_spans = [
        {
            'name': 'tests.test_auto_instrumentation.foo (pending)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'module_used_for_tests.py',
                'code.lineno': 123,
                'code.function': 'foo',
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': 'foo',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call foo',
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '0',
            },
        },
        {
            'name': IsStr(regex=r'tests.test_auto_instrumentation.(Foo.)?bar \(pending\)'),
            'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': IsStr(regex=r'(Foo.)?bar'),
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': IsStr(regex=r'(Foo.)?bar'),
                'logfire.msg_template': 'call {object}',
                'logfire.msg': IsStr(regex=r'call (Foo.)?bar'),
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '1',
            },
        },
        {
            'name': IsStr(regex=r'tests.test_auto_instrumentation.(Foo.)?bar'),
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': IsStr(regex=r'(Foo.)?bar'),
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': IsStr(regex=r'(Foo.)?bar'),
                'logfire.msg_template': 'call {object}',
                'logfire.msg': IsStr(regex=r'call (Foo.)?bar'),
                'logfire.span_type': 'span',
            },
        },
        *(
            (
                {
                    'name': IsStr(regex=r'tests.test_auto_instrumentation.(foo.\<locals\>.)?\<listcomp\> \(pending\)'),
                    'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                    'start_time': 4000000000,
                    'end_time': 4000000000,
                    'attributes': {
                        'code.filepath': 'test_auto_instrumentation.py',
                        'code.lineno': 123,
                        'code.function': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'code.namespace': 'tests.test_auto_instrumentation',
                        'object': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.msg_template': 'call {object}',
                        'logfire.msg': IsStr(regex=r'call (foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.span_type': 'pending_span',
                        'logfire.pending_parent_id': '1',
                    },
                },
                {
                    'name': IsStr(regex=r'tests.test_auto_instrumentation.(foo.\<locals\>.)?\<listcomp\>'),
                    'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'start_time': 4000000000,
                    'end_time': 5000000000,
                    'attributes': {
                        'code.filepath': 'test_auto_instrumentation.py',
                        'code.lineno': 123,
                        'code.function': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'code.namespace': 'tests.test_auto_instrumentation',
                        'object': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.msg_template': 'call {object}',
                        'logfire.msg': IsStr(regex=r'call (foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.span_type': 'span',
                    },
                },
            )
            if sys.version_info < (3, 12)
            else ()
        ),
        {
            'name': 'tests.test_auto_instrumentation.foo',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 4000000000 + listcomp_offset,
            'attributes': {
                'code.filepath': 'module_used_for_tests.py',
                'code.lineno': 123,
                'code.function': 'foo',
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': 'foo',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call foo',
                'logfire.span_type': 'span',
            },
        },
    ]

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == expected_spans


def test_auto_instrumentation_module_import(exporter: TestExporter) -> None:
    with ExitStack() as stack:
        stack.callback(uninstall_automatic_instrumentation)

        install_automatic_instrumentation()

        from .import_used_for_tests.a.b import wrap

        wrap(foo, 1)

    # On 3.12, list comprehensions do not generate a frame
    listcomp_offset = 2000000000
    if sys.version_info >= (3, 12):
        listcomp_offset = 0

    expected_spans = [
        {
            'name': 'tests.import_used_for_tests.<module> (pending)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': '<frozen importlib._bootstrap>',
                'code.lineno': 123,
                'code.function': '<module>',
                'code.namespace': 'tests.import_used_for_tests',
                'object': 'tests.import_used_for_tests',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call tests.import_used_for_tests',
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '0',
            },
        },
        {
            'name': 'tests.import_used_for_tests.<module>',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': '<frozen importlib._bootstrap>',
                'code.lineno': 123,
                'code.function': '<module>',
                'code.namespace': 'tests.import_used_for_tests',
                'object': 'tests.import_used_for_tests',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call tests.import_used_for_tests',
                'logfire.span_type': 'span',
            },
        },
        {
            'name': 'tests.import_used_for_tests.a.<module> (pending)',
            'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
            'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
            'start_time': 3000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': '<frozen importlib._bootstrap>',
                'code.lineno': 123,
                'code.function': '<module>',
                'code.namespace': 'tests.import_used_for_tests.a',
                'object': 'tests.import_used_for_tests.a',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call tests.import_used_for_tests.a',
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '0',
            },
        },
        {
            'name': 'tests.import_used_for_tests.a.<module>',
            'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
            'parent': None,
            'start_time': 3000000000,
            'end_time': 4000000000,
            'attributes': {
                'code.filepath': '<frozen importlib._bootstrap>',
                'code.lineno': 123,
                'code.function': '<module>',
                'code.namespace': 'tests.import_used_for_tests.a',
                'object': 'tests.import_used_for_tests.a',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call tests.import_used_for_tests.a',
                'logfire.span_type': 'span',
            },
        },
        {
            'name': 'tests.import_used_for_tests.a.b.<module> (pending)',
            'context': {'trace_id': 3, 'span_id': 6, 'is_remote': False},
            'parent': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
            'start_time': 5000000000,
            'end_time': 5000000000,
            'attributes': {
                'code.filepath': '<frozen importlib._bootstrap>',
                'code.lineno': 123,
                'code.function': '<module>',
                'code.namespace': 'tests.import_used_for_tests.a.b',
                'object': 'tests.import_used_for_tests.a.b',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call tests.import_used_for_tests.a.b',
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '0',
            },
        },
        {
            'name': 'tests.import_used_for_tests.a.b.<module>',
            'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
            'parent': None,
            'start_time': 5000000000,
            'end_time': 6000000000,
            'attributes': {
                'code.filepath': '<frozen importlib._bootstrap>',
                'code.lineno': 123,
                'code.function': '<module>',
                'code.namespace': 'tests.import_used_for_tests.a.b',
                'object': 'tests.import_used_for_tests.a.b',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call tests.import_used_for_tests.a.b',
                'logfire.span_type': 'span',
            },
        },
        {
            'name': 'tests.import_used_for_tests.a.b.wrap (pending)',
            'context': {'trace_id': 4, 'span_id': 8, 'is_remote': False},
            'parent': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
            'start_time': 7000000000,
            'end_time': 7000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': 'wrap',
                'code.namespace': 'tests.import_used_for_tests.a.b',
                'object': 'wrap',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call wrap',
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '0',
            },
        },
        {
            'name': 'tests.test_auto_instrumentation.foo (pending)',
            'context': {'trace_id': 4, 'span_id': 10, 'is_remote': False},
            'parent': {'trace_id': 4, 'span_id': 9, 'is_remote': False},
            'start_time': 8000000000,
            'end_time': 8000000000,
            'attributes': {
                'code.filepath': 'b.py',
                'code.lineno': 123,
                'code.function': 'foo',
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': 'foo',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call foo',
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '7',
            },
        },
        {
            'name': IsStr(regex=r'tests.test_auto_instrumentation(\.Foo)?.bar \(pending\)'),
            'context': {'trace_id': 4, 'span_id': 12, 'is_remote': False},
            'parent': {'trace_id': 4, 'span_id': 11, 'is_remote': False},
            'start_time': 9000000000,
            'end_time': 9000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': 'bar',
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': IsStr(regex=r'(Foo\.)?bar'),
                'logfire.msg_template': 'call {object}',
                'logfire.msg': IsStr(regex=r'call (Foo\.)?bar'),
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '9',
            },
        },
        {
            'name': IsStr(regex=r'tests.test_auto_instrumentation(\.Foo)?.bar'),
            'context': {'trace_id': 4, 'span_id': 11, 'is_remote': False},
            'parent': {'trace_id': 4, 'span_id': 9, 'is_remote': False},
            'start_time': 9000000000,
            'end_time': 10000000000,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': 'bar',
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': IsStr(regex=r'(Foo\.)?bar'),
                'logfire.msg_template': 'call {object}',
                'logfire.span_type': 'span',
                'logfire.msg': IsStr(regex=r'call (Foo\.)?bar'),
            },
        },
        *(
            (
                {
                    'name': IsStr(regex=r'tests.test_auto_instrumentation.(foo.\<locals\>.)?\<listcomp\> \(pending\)'),
                    'context': {'trace_id': 4, 'span_id': 14, 'is_remote': False},
                    'parent': {'trace_id': 4, 'span_id': 13, 'is_remote': False},
                    'start_time': 11000000000,
                    'end_time': 11000000000,
                    'attributes': {
                        'code.filepath': 'test_auto_instrumentation.py',
                        'code.lineno': 123,
                        'code.function': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'code.namespace': 'tests.test_auto_instrumentation',
                        'object': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.msg_template': 'call {object}',
                        'logfire.msg': IsStr(regex=r'call (foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.span_type': 'pending_span',
                        'logfire.pending_parent_id': '9',
                    },
                },
                {
                    'name': IsStr(regex=r'tests.test_auto_instrumentation.(foo.\<locals\>.)?\<listcomp\>'),
                    'context': {'trace_id': 4, 'span_id': 13, 'is_remote': False},
                    'parent': {'trace_id': 4, 'span_id': 9, 'is_remote': False},
                    'start_time': 11000000000,
                    'end_time': 12000000000,
                    'attributes': {
                        'code.filepath': 'test_auto_instrumentation.py',
                        'code.lineno': 123,
                        'code.function': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'code.namespace': 'tests.test_auto_instrumentation',
                        'object': IsStr(regex=r'(foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.msg_template': 'call {object}',
                        'logfire.msg': IsStr(regex=r'call (foo.\<locals\>.)?\<listcomp\>'),
                        'logfire.span_type': 'span',
                    },
                },
            )
            if sys.version_info < (3, 12)
            else ()
        ),
        {
            'name': 'tests.test_auto_instrumentation.foo',
            'context': {'trace_id': 4, 'span_id': 9, 'is_remote': False},
            'parent': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
            'start_time': 8000000000,
            'end_time': 11000000000 + listcomp_offset,
            'attributes': {
                'code.filepath': 'b.py',
                'code.lineno': 123,
                'code.function': 'foo',
                'code.namespace': 'tests.test_auto_instrumentation',
                'object': 'foo',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call foo',
                'logfire.span_type': 'span',
            },
        },
        {
            'name': 'tests.import_used_for_tests.a.b.wrap',
            'context': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
            'parent': None,
            'start_time': 7000000000,
            'end_time': 12000000000 + listcomp_offset,
            'attributes': {
                'code.filepath': 'test_auto_instrumentation.py',
                'code.lineno': 123,
                'code.function': 'wrap',
                'code.namespace': 'tests.import_used_for_tests.a.b',
                'object': 'wrap',
                'logfire.msg_template': 'call {object}',
                'logfire.msg': 'call wrap',
                'logfire.span_type': 'span',
            },
        },
    ]

    # insert_assert(exporter.exported_spans_as_dict(_include_pending_spans=True))
    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == expected_spans
