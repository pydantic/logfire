import contextlib
from collections import ChainMap
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.formatter import FormattingFailedWarning, chunks_formatter, logfire_format
from logfire._internal.scrubbing import NOOP_SCRUBBER, JsonPath, Scrubber
from logfire.testing import TestExporter


def chunks(format_string: str, kwargs: Mapping[str, Any]):
    result, _extra_attrs, _span_name = chunks_formatter.chunks(format_string, dict(kwargs), scrubber=Scrubber([]))
    return result


def test_simple_render():
    v = chunks('foo {bar}', {'bar': 'span'})
    assert v == [{'v': 'foo ', 't': 'lit'}, {'v': 'span', 't': 'arg'}]


def test_spec():
    v = chunks('foo {bar:0.2f}', ChainMap({}, {'bar': 123.456}))
    assert v == snapshot([{'t': 'lit', 'v': 'foo '}, {'t': 'arg', 'v': '123.46', 'spec': '0.2f'}])


def test_insert_name():
    v = chunks('foo {bar=}', {'bar': 42})
    assert v == snapshot([{'t': 'lit', 'v': 'foo bar='}, {'t': 'arg', 'v': '42'}])


def test_insert_name_spec():
    v = chunks('foo {bar=:d}', {'bar': 42})
    assert v == snapshot([{'t': 'lit', 'v': 'foo bar='}, {'t': 'arg', 'v': '42', 'spec': 'd'}])


def test_first():
    v = chunks('{bar}', {'bar': 42})
    assert v == snapshot([{'t': 'arg', 'v': '42'}])


def test_insert_first():
    v = chunks('{bar=}', {'bar': 42})
    assert v == snapshot([{'t': 'lit', 'v': 'bar='}, {'t': 'arg', 'v': '42'}])


def test_three():
    v = chunks('{foo} {bar} {spam}', ChainMap({'foo': 1, 'bar': 2}, {'spam': '3'}))
    assert v == snapshot(
        [
            {'t': 'arg', 'v': '1'},
            {'t': 'lit', 'v': ' '},
            {'t': 'arg', 'v': '2'},
            {'t': 'lit', 'v': ' '},
            {'t': 'arg', 'v': '3'},
        ]
    )


def test_dict():
    v = chunks('{foo[bar]}', {'foo': {'bar': 42}})
    assert v == snapshot([{'t': 'arg', 'v': '42'}])


def test_truncate():
    message = logfire_format(
        '1 {a} 2 {b} 3',
        dict(
            a='a' * 1000,
            b='b' * 1000,
        ),
        scrubber=Scrubber([]),
    )
    assert message == snapshot(
        '1 '
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        '...'
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        ' 2 '
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
        '...'
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
        ' 3'
    )
    assert len(message) == snapshot(261)


@contextlib.contextmanager
def warns_failed(msg: str):
    with pytest.warns(FormattingFailedWarning) as record:
        yield
    [warning] = record
    assert str(warning.message).endswith(f'The problem was: {msg}')


class BadRepr:
    def __repr__(self):
        raise ValueError('bad repr')


def test_conversion_error():
    with warns_failed('Error converting field {a}: bad repr'):
        logfire_format('{a!r}', {'a': BadRepr()}, NOOP_SCRUBBER)


def test_formatting_error():
    with warns_failed('Error formatting field {a}: bad repr'):
        logfire_format('{a}', {'a': BadRepr()}, NOOP_SCRUBBER)


def test_formatting_error_with_spec():
    with warns_failed("Error formatting field {a}: Unknown format code 'c' for object of type 'str'"):
        logfire_format('{a:c}', {'a': 'b'}, NOOP_SCRUBBER)


def test_format_spec_error():
    with warns_failed("Error formatting field {b}: Unknown format code 'c' for object of type 'str'"):
        logfire_format('{a:{b:c}}', {'a': '1', 'b': '2'}, NOOP_SCRUBBER)


def test_recursion_error():
    with warns_failed('Max format spec recursion exceeded'):
        logfire_format('{a:{a:{a:{a:5}}}}', {'a': 1}, NOOP_SCRUBBER)


def test_missing_field():
    with warns_failed('The field {a} is not defined.'):
        logfire_format('{a}', {}, NOOP_SCRUBBER)


def test_missing_field_with_dot():
    assert logfire_format('{a.b}', {'a.b': 123}, NOOP_SCRUBBER) == '123'
    assert logfire_format('{a.b}', {'a': SimpleNamespace(b=456), 'a.b': 123}, NOOP_SCRUBBER) == '456'

    with warns_failed("The fields 'a' and 'a.b' are not defined."):
        logfire_format('{a.b}', {'b': 1}, NOOP_SCRUBBER)


def test_missing_field_with_brackets():
    assert logfire_format('{a[b]}', {'a[b]': 123}, NOOP_SCRUBBER) == '123'
    assert logfire_format('{a[b]}', {'a': {'b': 456}, 'b': 1}, NOOP_SCRUBBER) == '456'

    with warns_failed("The fields 'a' and 'a[b]' are not defined."):
        logfire_format('{a[b]}', {'b': 1}, NOOP_SCRUBBER)


def test_missing_key_in_brackets():
    with warns_failed("The fields 'b' and 'a[b]' are not defined."):
        logfire_format('{a[b]}', {'a': {}, 'b': 1}, NOOP_SCRUBBER)


def test_empty_braces():
    with warns_failed('Empty curly brackets `{}` are not allowed. A field name is required.'):
        logfire_format('{}', {}, NOOP_SCRUBBER)


def test_empty_braces_in_brackets():
    with warns_failed('Error getting field {a[]}: Empty attribute in format string'):
        logfire_format('{a[]}', {'a': {}}, NOOP_SCRUBBER)


def test_numbered_fields():
    with warns_failed('Numeric field names are not allowed.'):
        logfire_format('{1}', {'1': 'a'}, NOOP_SCRUBBER)
    with warns_failed('Numeric field names are not allowed.'):
        logfire_format('{2.3}', {'2': 'a'}, NOOP_SCRUBBER)


def test_unbalanced_braces():
    """A message with unbalanced braces isn't a template, so it's kept as-is with a warning.

    Parsing such a string raises `ValueError`, which used to escape the normal formatting error handling
    and be reported as an internal error in Logfire.
    """
    with warns_failed("Single '{' encountered in format string"):
        assert logfire_format('value = {', {}, NOOP_SCRUBBER) == 'value = {'

    with warns_failed("Single '}' encountered in format string"):
        assert logfire_format('value = }', {}, NOOP_SCRUBBER) == 'value = }'

    with warns_failed("expected '}' before end of string"):
        assert logfire_format('a { b', {}, NOOP_SCRUBBER) == 'a { b'

    with warns_failed("unmatched '{' in format spec"):
        assert logfire_format('{a:{b}', {'a': 1, 'b': 2}, NOOP_SCRUBBER) == '{a:{b}'


def test_unbalanced_braces_still_logged(exporter: TestExporter):
    """A message with an unbalanced brace is logged as-is, not dropped as an internal error."""
    with pytest.warns(FormattingFailedWarning):
        logfire.info('value = {')

    [span] = exporter.exported_spans_as_dict()
    assert span['attributes']['logfire.msg'] == 'value = {'
    assert span['attributes']['logfire.msg_template'] == 'value = {'


class BadScrubber(Scrubber):
    def scrub_value(self, path: JsonPath, value: Any):
        raise ValueError('bad scrubber')


def test_internal_exception_formatting(caplog: pytest.LogCaptureFixture):
    assert logfire_format('{a}', {'a': 'b'}, BadScrubber([])) == '{a}'

    assert len(caplog.records) == 1
    assert caplog.records[0].message.startswith('Caught an internal error in Logfire.')
    assert str(caplog.records[0].exc_info[1]) == 'bad scrubber'  # type: ignore


@pytest.mark.anyio
async def test_await_in_fstring(exporter: TestExporter):
    """Test that logfire.info(f'{foo(await bar())}') evaluates the await expression and logs a warning."""

    async def bar() -> str:
        return 'content data'

    def foo(x: str) -> str:
        return x

    with pytest.warns(FormattingFailedWarning) as warnings:
        logfire.info(f'{foo(await bar())}')
        [warning] = warnings
        assert str(warning.message) == snapshot(
            '\n'
            '    Cannot evaluate await expression in f-string. Pre-evaluate the expression before logging.\n'
            '    For example, change:\n'
            '      logfire.info(f"{await get_value()}")\n'
            '    To:\n'
            '      value = await get_value()\n'
            '      logfire.info(f"{value}")\n'
            '    The problematic f-string value was: foo(await bar())'
        )

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': f'{foo(await bar())}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': f'{foo(await bar())}',
                    'logfire.msg': 'content data',
                    'code.filepath': 'test_formatter.py',
                    'code.lineno': 123,
                    'code.function': 'test_await_in_fstring',
                },
            }
        ]
    )


shadowed = 'global'


def test_nested_scope_in_fstring(exporter: TestExporter):
    """Generator expressions and lambdas in f-strings can use local variables."""
    items = [1, 2, 3]
    n = 10
    precision = 2
    shadowed = 'local'

    logfire.info(f'total {sum(y * n for y in items)}')
    logfire.info(f'lambda {(lambda: n)()}')
    logfire.info(f'spec {n:.{(lambda: precision)()}f}')
    # The local must win over the module global with the same name.
    logfire.info(f'shadow {next(shadowed for _ in items)}')
    # A keyword argument to the logging call wins over the local, as with plain names.
    logfire.info(f'kwarg {next(shadowed for _ in items)}', shadowed='kwarg')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'total {sum(y * n for y in items)}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'total {sum(y * n for y in items)}',
                    'logfire.msg': 'total 60',
                    'code.filepath': 'test_formatter.py',
                    'code.function': 'test_nested_scope_in_fstring',
                    'code.lineno': 123,
                    'sum(y * n for y in items)': 60,
                    'logfire.json_schema': '{"type":"object","properties":{"sum(y * n for y in items)":{}}}',
                },
            },
            {
                'name': 'lambda {(lambda: n)()}',
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'lambda {(lambda: n)()}',
                    'logfire.msg': 'lambda 10',
                    'code.filepath': 'test_formatter.py',
                    'code.function': 'test_nested_scope_in_fstring',
                    'code.lineno': 123,
                    '(lambda: n)()': 10,
                    'logfire.json_schema': '{"type":"object","properties":{"(lambda: n)()":{}}}',
                },
            },
            {
                'name': 'spec {n}',
                'context': {'trace_id': 3, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'spec {n}',
                    'logfire.msg': 'spec 10.00',
                    'code.filepath': 'test_formatter.py',
                    'code.function': 'test_nested_scope_in_fstring',
                    'code.lineno': 123,
                    'n': 10,
                    'logfire.json_schema': '{"type":"object","properties":{"n":{}}}',
                },
            },
            {
                'name': 'shadow {next(shadowed for _ in items)}',
                'context': {'trace_id': 4, 'span_id': 4, 'is_remote': False},
                'parent': None,
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'shadow {next(shadowed for _ in items)}',
                    'logfire.msg': 'shadow local',
                    'code.filepath': 'test_formatter.py',
                    'code.function': 'test_nested_scope_in_fstring',
                    'code.lineno': 123,
                    'next(shadowed for _ in items)': 'local',
                    'logfire.json_schema': '{"type":"object","properties":{"next(shadowed for _ in items)":{}}}',
                },
            },
            {
                'name': 'kwarg {next(shadowed for _ in items)}',
                'context': {'trace_id': 5, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'kwarg {next(shadowed for _ in items)}',
                    'logfire.msg': 'kwarg kwarg',
                    'code.filepath': 'test_formatter.py',
                    'code.function': 'test_nested_scope_in_fstring',
                    'code.lineno': 123,
                    'shadowed': 'kwarg',
                    'next(shadowed for _ in items)': 'kwarg',
                    'logfire.json_schema': '{"type":"object","properties":{"shadowed":{},"next(shadowed for _ in items)":{}}}',
                },
            },
        ]
    )
