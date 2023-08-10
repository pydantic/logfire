import pytest
from logfire import __version__
from logfire.observe import span
from logfire.observe._observe import MSG_TEMPLATE_KEY


def test_logfire_version() -> None:
    assert __version__ is not None


def test_span_without_kwargs() -> None:
    with pytest.raises(KeyError, match="'name'"):
        with span('test span', 'test {name}'):
            pass


def test_span_with_kwargs() -> None:
    with span('test span', 'test {name} {number}', name='foo', number=3, extra='extra') as s:
        pass

    assert s.name == 'test span'
    assert s.parent is None
    assert s.start_time < s.end_time
    assert s.attributes['name'] == 'foo'
    assert s.attributes['number'] == 3
    assert s.attributes['extra'] == 'extra'
    assert s.attributes[MSG_TEMPLATE_KEY] == 'test {name} {number}'
    assert len(s.events) == 1
    assert s.events[0].name == 'test foo 3'


def test_span_with_parent() -> None:
    with span('test parent span', '{type} span', type='parent') as p:
        with span('test child span', '{type} span', type='child') as c:
            pass

    assert p.name == 'test parent span'
    assert p.parent is None
    assert p.attributes['type'] == 'parent'
    assert p.attributes[MSG_TEMPLATE_KEY] == '{type} span'
    assert len(p.events) == 1
    assert p.events[0].name == 'parent span'

    assert c.name == 'test child span'
    assert c.parent == p.context
    assert c.attributes['type'] == 'child'
    assert c.attributes[MSG_TEMPLATE_KEY] == '{type} span'
    assert len(c.events) == 1
    assert c.events[0].name == 'child span'
