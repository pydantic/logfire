from logfire.formatter import chunks_formatter


def test_simple_render():
    v = chunks_formatter.chunks('foo {bar}', [{'bar': 'span'}])
    assert v == [{'v': 'foo ', 't': 'lit'}, {'v': 'span', 't': 'arg'}]


def test_spec():
    v = chunks_formatter.chunks('foo {bar:0.2f}', [{}, {'bar': 123.456}])
    # insert_assert(v)
    assert v == [{'t': 'lit', 'v': 'foo '}, {'t': 'arg', 'v': '123.46', 'spec': '0.2f'}]


def test_insert_name():
    v = chunks_formatter.chunks('foo {bar=}', [{'bar': 42}])
    # insert_assert(v)
    assert v == [{'t': 'lit', 'v': 'foo bar='}, {'t': 'arg', 'v': '42'}]


def test_insert_name_spec():
    v = chunks_formatter.chunks('foo {bar=:d}', [{'bar': 42}])
    # insert_assert(v)
    assert v == [{'t': 'lit', 'v': 'foo bar='}, {'t': 'arg', 'v': '42', 'spec': 'd'}]


def test_first():
    v = chunks_formatter.chunks('{bar}', [{'bar': 42}])
    # insert_assert(v)
    assert v == [{'t': 'arg', 'v': '42'}]


def test_insert_first():
    v = chunks_formatter.chunks('{bar=}', [{'bar': 42}])
    # insert_assert(v)
    assert v == [{'t': 'lit', 'v': 'bar='}, {'t': 'arg', 'v': '42'}]


def test_three():
    v = chunks_formatter.chunks('{foo} {bar} {spam}', [{'foo': 1, 'bar': 2}, {'spam': '3'}])
    # insert_assert(v)
    assert v == [
        {'t': 'arg', 'v': '1'},
        {'t': 'lit', 'v': ' '},
        {'t': 'arg', 'v': '2'},
        {'t': 'lit', 'v': ' '},
        {'t': 'arg', 'v': '3'},
    ]


def test_dict():
    v = chunks_formatter.chunks('{foo[bar]}', [{'foo': {'bar': 42}}])
    # insert_assert(v)
    assert v == [{'t': 'arg', 'v': '42'}]
