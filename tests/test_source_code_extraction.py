from __future__ import annotations

import sys
from typing import Any

import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.formatter import InspectArgumentsFailedWarning
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
                    'code.lineno': 15,
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
                    'code.lineno': 21,
                    'code.function': code_function,
                    'logfire.msg_template': 'from method',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'from method',
                },
            }
        ]
    )


@pytest.mark.skipif(
    sys.version_info[:2] == (3, 8), reason='Warning is only raised in Python 3.9+ because f-string magic is enabled'
)
def test_source_code_extraction_module(exporter: TestExporter) -> None:
    with pytest.warns(InspectArgumentsFailedWarning, match='No source code available'):
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
                'name': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
No source code available. This happens when running in an interactive shell, using exec(), or running .pyc files without the source .py files.\
""",
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
No source code available. This happens when running in an interactive shell, using exec(), or running .pyc files without the source .py files.\
""",
                    'logfire.msg': """\
Failed to introspect calling code. Please report this issue to Logfire. Falling back to normal message formatting which may result in loss of information if using an f-string. Set inspect_arguments=False in logfire.configure() to suppress this warning. The problem was:
No source code available. This happens when running in an interactive shell, using exec(), or running .pyc files without the source .py files.\
""",
                    'code.filepath': 'tests/test_source_code_extraction.py',
                    'code.function': 'test_source_code_extraction_module',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'from module',
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'tests/test_source_code_extraction.py',
                    'code.function': 'test_source_code_extraction_module',
                    'code.lineno': 123,
                    'logfire.msg_template': 'from module',
                    'logfire.msg': 'from module',
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
                    'code.lineno': 29,
                    'code.function': code_function,
                    'logfire.msg_template': 'hi!',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'hi!',
                },
            }
        ]
    )
