from collections import ChainMap

from inline_snapshot import snapshot

from logfire._formatter import chunks_formatter, logfire_format


def test_simple_render():
    v = chunks_formatter.chunks('foo {bar}', {'bar': 'span'})
    assert v == [{'v': 'foo ', 't': 'lit'}, {'v': 'span', 't': 'arg'}]


def test_spec():
    v = chunks_formatter.chunks('foo {bar:0.2f}', ChainMap({}, {'bar': 123.456}))
    # insert_assert(v)
    assert v == [{'t': 'lit', 'v': 'foo '}, {'t': 'arg', 'v': '123.46', 'spec': '0.2f'}]


def test_insert_name():
    v = chunks_formatter.chunks('foo {bar=}', {'bar': 42})
    # insert_assert(v)
    assert v == [{'t': 'lit', 'v': 'foo bar='}, {'t': 'arg', 'v': '42'}]


def test_insert_name_spec():
    v = chunks_formatter.chunks('foo {bar=:d}', {'bar': 42})
    # insert_assert(v)
    assert v == [{'t': 'lit', 'v': 'foo bar='}, {'t': 'arg', 'v': '42', 'spec': 'd'}]


def test_first():
    v = chunks_formatter.chunks('{bar}', {'bar': 42})
    # insert_assert(v)
    assert v == [{'t': 'arg', 'v': '42'}]


def test_insert_first():
    v = chunks_formatter.chunks('{bar=}', {'bar': 42})
    # insert_assert(v)
    assert v == [{'t': 'lit', 'v': 'bar='}, {'t': 'arg', 'v': '42'}]


def test_three():
    v = chunks_formatter.chunks('{foo} {bar} {spam}', ChainMap({'foo': 1, 'bar': 2}, {'spam': '3'}))
    # insert_assert(v)
    assert v == [
        {'t': 'arg', 'v': '1'},
        {'t': 'lit', 'v': ' '},
        {'t': 'arg', 'v': '2'},
        {'t': 'lit', 'v': ' '},
        {'t': 'arg', 'v': '3'},
    ]


def test_dict():
    v = chunks_formatter.chunks('{foo[bar]}', {'foo': {'bar': 42}})
    # insert_assert(v)
    assert v == [{'t': 'arg', 'v': '42'}]


def test_truncate():
    message = logfire_format(
        '1 {a} 2 {b} 3',
        dict(
            a='a' * 1000,
            b='b' * 1000,
        ),
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
