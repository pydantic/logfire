from __future__ import annotations

import ast
import sys
from typing import Any

import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal import ast_utils
from logfire._internal.ast_utils import InspectArgumentsFailedWarning
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
        if 'attributes' in span:  # pragma: no branch
            if 'code.filepath' in span['attributes']:  # pragma: no branch
                span['attributes']['code.filepath'] = span['attributes']['code.filepath'].replace(
                    'src/packages/logfire/', ''
                )
    return spans


def test_source_code_extraction_function(exporter: TestExporter) -> None:
    func()

    assert normalize_filepaths(
        exporter.exported_spans_as_dict(strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False)
    ) == snapshot(
        [
            {
                'name': 'from function',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'tests/test_source_code_extraction.py',
                    'code.lineno': 17,
                    'code.function': 'func',
                    'logfire.msg_template': 'from function',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'from function',
                },
            }
        ]
    )


def test_source_code_extraction_method(exporter: TestExporter) -> None:
    AClass().method()

    code_function = 'AClass.method' if sys.version_info >= (3, 11) else 'method'
    assert normalize_filepaths(
        exporter.exported_spans_as_dict(strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False)
    ) == snapshot(
        [
            {
                'name': 'from method',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'tests/test_source_code_extraction.py',
                    'code.lineno': 23,
                    'code.function': code_function,
                    'logfire.msg_template': 'from method',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'from method',
                },
            }
        ]
    )


def test_source_code_extraction_module(exporter: TestExporter, recwarn: pytest.WarningsRecorder) -> None:
    # exec() has no source for `executing` to read. A literal template with
    # explicit kwargs does not need inspection, so this must not warn (#2223).
    exec(
        """import logfire
with logfire.span('from {name}', name='module'):
    pass
    """
    )
    assert [w for w in recwarn if w.category is InspectArgumentsFailedWarning] == []

    assert normalize_filepaths(
        exporter.exported_spans_as_dict(strip_filepaths=False, _strip_function_qualname=False)
    ) == snapshot(
        [
            {
                'name': 'from {name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'tests/test_source_code_extraction.py',
                    'code.function': 'test_source_code_extraction_module',
                    'code.lineno': 123,
                    'name': 'module',
                    'logfire.msg_template': 'from {name}',
                    'logfire.msg': 'from module',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{}}}',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_source_code_extraction_exec_no_inspect_arguments(
    exporter: TestExporter, config_kwargs: dict[str, Any]
) -> None:
    config_kwargs['inspect_arguments'] = False
    logfire.configure(**config_kwargs)
    exec(
        """import logfire
with logfire.span('from module'):
    pass
"""
    )

    assert normalize_filepaths(
        exporter.exported_spans_as_dict(strip_filepaths=False, _strip_function_qualname=False)
    ) == snapshot(
        [
            {
                'name': 'from module',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'tests/test_source_code_extraction.py',
                    'code.function': 'test_source_code_extraction_exec_no_inspect_arguments',
                    'code.lineno': 123,
                    'logfire.msg_template': 'from module',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'from module',
                },
            }
        ]
    )


def test_source_code_extraction_nested(exporter: TestExporter) -> None:
    nested()

    code_function = 'nested.<locals>.bar.<locals>.AClass.method' if sys.version_info >= (3, 11) else 'method'
    assert normalize_filepaths(
        exporter.exported_spans_as_dict(strip_filepaths=False, fixed_line_number=None, _strip_function_qualname=False)
    ) == snapshot(
        [
            {
                'name': 'hi!',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'tests/test_source_code_extraction.py',
                    'code.lineno': 31,
                    'code.function': code_function,
                    'logfire.msg_template': 'hi!',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'hi!',
                },
            }
        ]
    )


def test_get_node_source_text_falls_back_to_unparse(monkeypatch: pytest.MonkeyPatch) -> None:
    node = ast.parse('x', mode='eval').body

    class Source:
        text = 'x'

    def get_source_segment(*args: Any) -> str:
        return 'x +'

    monkeypatch.setattr(ast, 'get_source_segment', get_source_segment)

    assert ast_utils.get_node_source_text(node, Source()) == 'x'
