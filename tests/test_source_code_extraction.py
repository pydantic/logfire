from __future__ import annotations

import sys
from typing import Any

import logfire
from logfire.testing import TestExporter


def func() -> None:
    with logfire.span('from function'):
        pass


class AClass:
    def method(self) -> None:
        with logfire.span('from method'):
            pass


def nested() -> None:
    def bar() -> None:
        class AClass:
            def method(self) -> None:
                with logfire.span('hi!'):
                    pass

        AClass().method()

    bar()


def normalize_filepaths(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Allow these tests to run from the monorepo root directory of sdk source directory"""
    for span in spans:
        if 'attributes' in span:
            if 'code.filepath' in span['attributes']:
                span['attributes']['code.filepath'] = span['attributes']['code.filepath'].replace(
                    'src/packages/logfire/', ''
                )
    return spans


def test_source_code_extraction_function(exporter: TestExporter) -> None:
    func()

    # insert_assert(normalize_filepaths(exporter.exported_spans_as_dict(strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False)))
    assert normalize_filepaths(
        exporter.exported_spans_as_dict(strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False)
    ) == [
        {
            'name': 'from function',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': 'tests/test_source_code_extraction.py',
                'code.lineno': 11,
                'code.function': 'func',
                'logfire.msg_template': 'from function',
                'logfire.span_type': 'span',
                'logfire.msg': 'from function',
            },
        }
    ]


def test_source_code_extraction_method(exporter: TestExporter) -> None:
    AClass().method()

    if sys.version_info >= (3, 11):
        # insert_assert(normalize_filepaths(exporter.exported_spans_as_dict(strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False)))
        assert normalize_filepaths(
            exporter.exported_spans_as_dict(
                strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False
            )
        ) == [
            {
                'name': 'from method',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'tests/test_source_code_extraction.py',
                    'code.lineno': 17,
                    'code.function': 'AClass.method',
                    'logfire.msg_template': 'from method',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'from method',
                },
            }
        ]
    else:
        # insert_assert(normalize_filepaths(exporter.exported_spans_as_dict(strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False)))
        assert normalize_filepaths(
            exporter.exported_spans_as_dict(
                strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False
            )
        ) == [
            {
                'name': 'from method',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'tests/test_source_code_extraction.py',
                    'code.lineno': 17,
                    'code.function': 'method',
                    'logfire.msg_template': 'from method',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'from method',
                },
            }
        ]


def test_source_code_extraction_module(exporter: TestExporter) -> None:
    exec(
        """import logfire
with logfire.span('from module'):
    pass
"""
    )

    # insert_assert(normalize_filepaths(exporter.exported_spans_as_dict(strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False)))
    assert normalize_filepaths(
        exporter.exported_spans_as_dict(strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False)
    ) == [
        {
            'name': 'from module',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'code.filepath': '<string>',
                'code.lineno': 2,
                'logfire.msg_template': 'from module',
                'logfire.span_type': 'span',
                'logfire.msg': 'from module',
            },
        }
    ]


def test_source_code_extraction_nested(exporter: TestExporter) -> None:
    nested()

    if sys.version_info >= (3, 11):  # pragma: no branch
        # insert_assert(normalize_filepaths(exporter.exported_spans_as_dict(strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False)))
        assert normalize_filepaths(
            exporter.exported_spans_as_dict(
                strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False
            )
        ) == [
            {
                'name': 'hi!',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'tests/test_source_code_extraction.py',
                    'code.lineno': 25,
                    'code.function': 'nested.<locals>.bar.<locals>.AClass.method',
                    'logfire.msg_template': 'hi!',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'hi!',
                },
            }
        ]
    else:  # pragma: no cover
        # insert_assert(normalize_filepaths(exporter.exported_spans_as_dict(strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False)))
        assert normalize_filepaths(
            exporter.exported_spans_as_dict(
                strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False
            )
        ) == [
            {
                'name': 'hi!',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'tests/test_source_code_extraction.py',
                    'code.lineno': 25,
                    'code.function': 'method',
                    'logfire.msg_template': 'hi!',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'hi!',
                },
            }
        ]
