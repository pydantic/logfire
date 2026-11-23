import contextlib
from collections import ChainMap
from collections.abc import Mapping
from types import FrameType, SimpleNamespace
from typing import Any

import executing
import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal import formatter
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


@pytest.mark.parametrize(
    'key', ['name', 'first name', 'content-type', 'service.name', '__class__', 'café', '日本語', 'a_1 .-']
)
def test_allowed_lookup_keys(key: str):
    assert logfire_format('{value[' + key + ']}', {'value': {key: 42}}, NOOP_SCRUBBER) == '42'


@pytest.mark.parametrize(
    'key',
    ['call()', '"name"', "'name'", 'a[b', 'a+b', 'a/b', 'a:b', 'a;b', 'a\\b', 'a\tb', 'a\nb', '__import__("os")'],
)
@pytest.mark.parametrize('template', ['{value[KEY]}', '{value[safe][KEY]}', '{number:{value[KEY]}}'])
def test_rejected_lookup_keys(key: str, template: str):
    class UnexpectedLookup:
        def __getitem__(self, key: str) -> Any:
            pytest.fail('Invalid keys must be rejected before any subscription is performed')

    template = template.replace('KEY', key)
    with pytest.warns(FormattingFailedWarning, match='Square bracket lookup keys may only contain'):
        assert logfire_format(template, {'value': UnexpectedLookup(), 'number': 1}, NOOP_SCRUBBER) == template


def test_lookup_indices_and_dunder_attributes():
    assert logfire_format('{value[0]}', {'value': [42]}, NOOP_SCRUBBER) == '42'
    assert logfire_format('{value.__class__.__name__}', {'value': 42}, NOOP_SCRUBBER) == 'int'


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


def test_nested_scope_in_fstring(exporter: TestExporter):
    """A lambda, generator expression or comprehension in an f-string isn't evaluated again, so warn."""
    items = [1, 2, 3]
    n = 10
    precision = 2
    name = 'local'

    with pytest.warns(FormattingFailedWarning) as warnings:
        logfire.info(f'joined {", ".join(str(y) for y in items)}')
        logfire.info(f'doubled {[y * 2 for y in items]}')
        logfire.info(f'lambda {(lambda: n)()}')
        logfire.info(f'spec {n:.{(lambda: precision)()}f}')
        # Evaluated again, the generator expression would look up `name` in the module globals
        logfire.info(f'name {next(name for _ in items)}', name='kwarg')

    assert [str(w.message).splitlines()[-1].strip() for w in warnings] == snapshot(
        [
            'The problem was: Cannot evaluate the f-string value {", ".join(str(y) for y in items)} because it contains a lambda, generator expression or comprehension. Assign the value to a variable before logging.',
            'The problem was: Cannot evaluate the f-string value {[y * 2 for y in items]} because it contains a lambda, generator expression or comprehension. Assign the value to a variable before logging.',
            'The problem was: Cannot evaluate the f-string value {(lambda: n)()} because it contains a lambda, generator expression or comprehension. Assign the value to a variable before logging.',
            'The problem was: Cannot evaluate the f-string value {n} because it contains a lambda, generator expression or comprehension. Assign the value to a variable before logging.',
            'The problem was: Cannot evaluate the f-string value {next(name for _ in items)} because it contains a lambda, generator expression or comprehension. Assign the value to a variable before logging.',
        ]
    )
    assert [
        (span['attributes']['logfire.msg_template'], span['attributes']['logfire.msg'])
        for span in exporter.exported_spans_as_dict()
    ] == snapshot(
        [
            ('joined 1, 2, 3', 'joined 1, 2, 3'),
            ('doubled [2, 4, 6]', 'doubled [2, 4, 6]'),
            ('lambda 10', 'lambda 10'),
            ('spec 10.00', 'spec 10.00'),
            ('name local', 'name local'),
        ]
    )


def test_private_names_in_fstring(exporter: TestExporter):
    """Private names in an f-string inside a class are evaluated again with the same mangling as the compiler."""

    class Account:
        __currency = 'EUR'

        def __init__(self, balance: float):
            self.__balance = balance

        def report(self):
            __width = 6
            logfire.info(f'balance {self.__balance:{__width}.2f} {self.__currency} {self.__class__.__name__}')

    Account(12.5).report()

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'balance {self.__balance} {self.__currency} {self.__class__.__name__}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'balance {self.__balance} {self.__currency} {self.__class__.__name__}',
                    'logfire.msg': 'balance  12.50 EUR Account',
                    'code.filepath': 'test_formatter.py',
                    'code.function': 'report',
                    'code.lineno': 123,
                    'self.__balance': 12.5,
                    'self.__currency': 'EUR',
                    'self.__class__.__name__': 'Account',
                    'logfire.json_schema': '{"type":"object","properties":{"self.__balance":{},"self.__currency":{},"self.__class__.__name__":{}}}',
                },
            }
        ]
    )


def test_private_names_in_nested_classes_and_functions(exporter: TestExporter):
    class Outer:
        __value = 'outer'
        logfire.info(f'outer body {__value}')

        class Inner:
            __value = 'inner'
            logfire.info(f'inner body {__value}')

            def report(self):
                logfire.info(f'inner method {self.__value}')
                __local = 'closure'

                def report_closure():
                    logfire.info(f'nested function {__local}')

                report_closure()

    Outer.Inner().report()

    assert [
        (span['attributes']['logfire.msg_template'], span['attributes']['logfire.msg'])
        for span in exporter.exported_spans_as_dict()
    ] == snapshot(
        [
            ('outer body {__value}', 'outer body outer'),
            ('inner body {__value}', 'inner body inner'),
            ('inner method {self.__value}', 'inner method inner'),
            ('nested function {__local}', 'nested function closure'),
        ]
    )


def test_private_names_with_underscore_class_names(exporter: TestExporter):
    class __Leading:
        __value = 'leading underscores'

        def report(self):
            logfire.info(f'value {self.__value}')

    class ___:
        __value = 'only underscores'

        def report(self):
            logfire.info(f'value {self.__value}')

    __Leading().report()
    ___().report()

    assert [
        (span['attributes']['logfire.msg_template'], span['attributes']['self.__value'])
        for span in exporter.exported_spans_as_dict()
    ] == snapshot([('value {self.__value}', 'leading underscores'), ('value {self.__value}', 'only underscores')])


def test_private_names_in_class_decorators_and_bases(exporter: TestExporter):
    def decorator(_message: None):
        def decorate(cls: type):
            return cls

        return decorate

    def base(_message: None):
        return object

    __value = 'function'

    @decorator(logfire.info(f'outside decorator {__value}'))
    class Outside(base(logfire.info(f'outside base {__value}'))):
        __value = 'outside class'

    class Outer:
        __value = 'outer'

        @decorator(logfire.info(f'outer decorator {__value}'))
        class Inner(base(logfire.info(f'outer base {__value}'))):
            __value = 'inner'

    assert Outer.Inner.__name__ == 'Inner'

    assert [
        (span['attributes']['logfire.msg_template'], span['attributes']['__value'])
        for span in exporter.exported_spans_as_dict()
    ] == snapshot(
        [
            ('outside decorator {__value}', 'function'),
            ('outside base {__value}', 'function'),
            ('outer decorator {__value}', 'outer'),
            ('outer base {__value}', 'outer'),
        ]
    )


def test_private_and_already_mangled_names_in_fstring(exporter: TestExporter):
    class Account:
        _Account__balance: float

        def __init__(self):
            self.__balance = 12.5

        def report(self):
            logfire.info(f'balance {self.__balance + self._Account__balance}')
            logfire.info(f'keyword {dict(__balance=self.__balance)}')

    Account().report()

    assert [
        (span['attributes']['logfire.msg_template'], span['attributes']['logfire.msg'])
        for span in exporter.exported_spans_as_dict()
    ] == snapshot(
        [
            ('balance {self.__balance + self._Account__balance}', 'balance 25.0'),
            ('keyword {dict(__balance=self.__balance)}', "keyword {'__balance': 12.5}"),
        ]
    )


def test_logfire_calls_skip_fstring_magic(exporter: TestExporter, monkeypatch: pytest.MonkeyPatch):
    """Spans that logfire opens itself don't run `executing` on their call site (#2771)."""
    # In tests, logfire's own calls are checked for f-strings, which needs `executing`. Turn that off.
    monkeypatch.delenv('PYTEST_CURRENT_TEST')
    inspected: list[str] = []
    real_executing = executing.Source.executing.__func__

    def spy(cls: type[executing.Source], frame: FrameType) -> Any:
        inspected.append(frame.f_code.co_filename)
        return real_executing(cls, frame)

    monkeypatch.setattr(executing.Source, 'executing', classmethod(spy))

    with logfire.var('my_flag', type=bool, default=False).get():
        pass
    assert inspected == []

    # Calls from user code still get the magic.
    x = 1
    logfire.info(f'user {x}')
    assert inspected == [__file__]

    assert [span['attributes']['logfire.msg_template'] for span in exporter.exported_spans_as_dict()] == snapshot(
        ['Resolve variable my_flag', 'user {x}']
    )


def test_logfire_fstring_call_fails_in_tests(exporter: TestExporter, monkeypatch: pytest.MonkeyPatch):
    """In tests, an f-string passed by logfire's own code is an error, since the magic is skipped for it."""
    monkeypatch.setattr(formatter, 'is_logfire_code', lambda code: code.co_filename == __file__)  # type: ignore

    x = 1
    with pytest.raises(AssertionError, match='Logfire called itself with an f-string'):
        logfire.info(f'internal {x}')

    # Re-evaluating the expression can fail, and that must not hide the f-string either.
    calls: list[int] = []

    def fails_when_called_again() -> int:
        calls.append(1)
        if len(calls) > 1:
            raise RuntimeError('called again')
        return x

    with pytest.raises(RuntimeError, match='called again'):
        logfire.info(f'internal {fails_when_called_again()}')

    logfire.info('internal {x}', x=x)
    assert [span['attributes']['logfire.msg'] for span in exporter.exported_spans_as_dict()] == snapshot(['internal 1'])
