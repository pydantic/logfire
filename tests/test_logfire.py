import pytest
from logfire import __version__
from logfire.observe._observe import LEVEL_KEY, LOG_TYPE_KEY, MSG_TEMPLATE_KEY


def test_logfire_version() -> None:
    assert __version__ is not None


def test_span_without_kwargs(observe) -> None:
    with pytest.raises(KeyError, match="'name'"):
        with observe.span('test span', 'test {name}'):
            pass


def test_span_with_kwargs(observe) -> None:
    with observe.span('test span', 'test {name} {number}', name='foo', number=3, extra='extra') as s:
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


def test_span_with_parent(observe) -> None:
    with observe.span('test parent span', '{type} span', type='parent') as p:
        with observe.span('test child span', '{type} span', type='child') as c:
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


@pytest.mark.parametrize('level', ('critical', 'debug', 'error', 'info', 'notice', 'warning'))
def test_log(observe, exporter, level):
    getattr(observe, level)('test {name} {number}', name='foo', number=2)

    observe._telemetry.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.attributes[LEVEL_KEY] == level
    assert s.attributes[MSG_TEMPLATE_KEY] == 'test {name} {number}'
    assert s.attributes[LOG_TYPE_KEY] == 'log'
    assert s.attributes['name'] == 'foo'
    assert s.attributes['number'] == 2
