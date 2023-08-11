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
    with observe.span('test span', 'test {name=} {number}', name='foo', number=3, extra='extra') as s:
        pass

    assert s['real_span'].name == 'test span'
    assert s['real_span'].parent is None
    assert s['real_span'].start_time < s['real_span'].end_time
    assert len(s['real_span'].events) == 0
    assert s['start_span'].name == 'test name=foo 3'
    assert s['start_span'].attributes['name'] == 'foo'
    assert s['start_span'].attributes['number'] == 3
    assert s['start_span'].attributes['extra'] == 'extra'
    assert s['start_span'].attributes[MSG_TEMPLATE_KEY] == 'test {name=} {number}'


def test_span_with_parent(observe) -> None:
    with observe.span('test parent span', '{type} span', type='parent') as p:
        with observe.span('test child span', '{type} span', type='child') as c:
            pass

    assert p['real_span'].name == 'test parent span'
    assert p['real_span'].parent is None
    assert len(p['real_span'].events) == 0
    assert p['start_span'].attributes['type'] == 'parent'
    assert p['start_span'].attributes[MSG_TEMPLATE_KEY] == '{type} span'

    assert c['real_span'].name == 'test child span'
    assert c['real_span'].parent == p['real_span'].context
    assert len(c['real_span'].events) == 0
    assert c['start_span'].attributes['type'] == 'child'
    assert c['start_span'].attributes[MSG_TEMPLATE_KEY] == '{type} span'


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


def test_log_equals(observe, exporter) -> None:
    observe.info('test message {foo=} {bar=}', foo='foo', bar=3)

    observe._telemetry.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.name == 'test message foo=foo bar=3'
    assert s.attributes['foo'] == 'foo'
    assert s.attributes['bar'] == 3
    assert s.attributes[MSG_TEMPLATE_KEY] == 'test message {foo=} {bar=}'
    assert s.attributes[LEVEL_KEY] == 'info'
    assert s.attributes[LOG_TYPE_KEY] == 'log'
