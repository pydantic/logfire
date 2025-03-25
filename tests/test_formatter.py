import ast
import contextlib
import sys
from collections import ChainMap
from types import CodeType, SimpleNamespace
from typing import Any, Mapping

import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.constants import ATTRIBUTES_MESSAGE_KEY
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


class BadScrubber(Scrubber):
    def scrub_value(self, path: JsonPath, value: Any):
        raise ValueError('bad scrubber')


def test_internal_exception_formatting(caplog: pytest.LogCaptureFixture):
    assert logfire_format('{a}', {'a': 'b'}, BadScrubber([])) == '{a}'

    assert len(caplog.records) == 1
    assert caplog.records[0].message.startswith('Caught an internal error in Logfire.')
    assert str(caplog.records[0].exc_info[1]) == 'bad scrubber'  # type: ignore


@pytest.mark.skipif(sys.version_info[:2] == (3, 8), reason='fstring magic is only for 3.9+')
def test_syntax_error_in_ast_walk(monkeypatch: pytest.MonkeyPatch):
    """Test the SyntaxError exception handling in ast.walk when checking for await expressions."""

    def mock_ast_walk(*args: object, **kwargs: object) -> None:
        raise SyntaxError('Simulated syntax error in ast.walk')

    monkeypatch.setattr(ast, 'walk', mock_ast_walk)

    node = ast.FormattedValue(value=ast.Name(id='test', ctx=ast.Load()), conversion=-1, format_spec=None)

    class MockSource:
        text = 'test'

    # This should not raise an exception because the SyntaxError is caught
    from logfire._internal.formatter import compile_formatted_value

    _, value_code, formatted_code = compile_formatted_value(node, MockSource())

    assert isinstance(value_code, CodeType)
    assert isinstance(formatted_code, CodeType)


@pytest.mark.skipif(sys.version_info[:2] == (3, 8), reason='fstring magic is only for 3.9+')
def test_await_in_fstring(exporter: TestExporter):
    """Test that logfire.info(f'{foo(await bar())}') evaluates the await expression and logs a warning."""
    import asyncio

    async def bar() -> str:
        return 'content data'

    def foo(x: str) -> str:
        return x

    async def test_log() -> None:
        with pytest.warns(FormattingFailedWarning) as warnings:
            logfire.info(f'{foo(await bar())}')
            [warning] = warnings
            assert str(warning.message) == snapshot(
                '\n'
                '    Ensure you are either:\n'
                '      (1) passing an f-string directly, with inspect_arguments enabled and working, or\n'
                '      (2) passing a literal `str.format`-style template, not a preformatted string.\n'
                '    See https://logfire.pydantic.dev/docs/guides/onboarding-checklist/add-manual-tracing/#messages-and-span-names.\n'
                '    The problem was: Cannot evaluate await expression in f-string: foo(await bar()). Pre-evaluate the expression before logging.'
            )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(test_log())
        assert len(exporter.exported_spans) == 1
        span = exporter.exported_spans[0]
        assert span.attributes is not None
        assert span.attributes[ATTRIBUTES_MESSAGE_KEY] == snapshot('content data')
    finally:
        loop.close()
