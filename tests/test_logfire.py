import pytest
from opentelemetry.trace import format_span_id

from logfire import Observe, __version__
from logfire._observe import LEVEL_KEY, LOG_TYPE_KEY, MSG_TEMPLATE_KEY, START_PARENT_ID, TAGS_KEY


def test_logfire_version() -> None:
    assert __version__ is not None


def test_span_without_kwargs(observe: Observe) -> None:
    with pytest.raises(KeyError, match="'name'"):
        with observe.span('test span', 'test {name}'):
            pass


def test_span_with_kwargs(observe: Observe) -> None:
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
    assert TAGS_KEY not in s['real_span'].attributes


def test_span_with_parent(observe: Observe) -> None:
    with observe.span('test parent span', '{type} span', type='parent') as p:
        with observe.span('test child span', '{type} span', type='child') as c:
            pass

    assert p['real_span'].name == 'test parent span'
    assert p['real_span'].parent is None
    assert len(p['real_span'].events) == 0
    assert p['start_span'].attributes['type'] == 'parent'
    assert p['start_span'].attributes[MSG_TEMPLATE_KEY] == '{type} span'
    assert TAGS_KEY not in p['real_span'].attributes

    assert c['real_span'].name == 'test child span'
    assert c['real_span'].parent == p['real_span'].context
    assert len(c['real_span'].events) == 0
    assert c['start_span'].attributes['type'] == 'child'
    assert c['start_span'].attributes[MSG_TEMPLATE_KEY] == '{type} span'
    assert TAGS_KEY not in c['real_span'].attributes

    p_real_span_span_id = p['real_span'].context.span_id
    c_start_span_start_parent_id = c['start_span'].attributes[START_PARENT_ID]
    assert format_span_id(p_real_span_span_id) == c_start_span_start_parent_id


def test_span_with_tags(observe: Observe) -> None:
    with observe.tags('tag1', 'tag2').span(
        'test span', 'test {name} {number}', name='foo', number=3, extra='extra'
    ) as s:
        pass

    assert s['real_span'].name == 'test span'
    assert s['real_span'].parent is None
    assert s['real_span'].start_time < s['real_span'].end_time
    assert s['start_span'].attributes['name'] == 'foo'
    assert s['start_span'].attributes['number'] == 3
    assert s['start_span'].attributes['extra'] == 'extra'
    assert s['start_span'].attributes[MSG_TEMPLATE_KEY] == 'test {name} {number}'
    assert s['real_span'].attributes[TAGS_KEY] == ('tag1', 'tag2')
    assert len(s['real_span'].events) == 0


@pytest.mark.parametrize('level', ('critical', 'debug', 'error', 'info', 'notice', 'warning'))
def test_log(observe: Observe, exporter, level):
    getattr(observe, level)('test {name} {number}', name='foo', number=2)

    observe._client.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.attributes[LEVEL_KEY] == level
    assert s.attributes[MSG_TEMPLATE_KEY] == 'test {name} {number}'
    assert s.attributes[LOG_TYPE_KEY] == 'log'
    assert s.attributes['name'] == 'foo'
    assert s.attributes['number'] == 2
    assert TAGS_KEY not in s.attributes


def test_log_equals(observe: Observe, exporter) -> None:
    observe.info('test message {foo=} {bar=}', foo='foo', bar=3)

    observe._client.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.name == 'test message foo=foo bar=3'
    assert s.attributes['foo'] == 'foo'
    assert s.attributes['bar'] == 3
    assert s.attributes[MSG_TEMPLATE_KEY] == 'test message {foo=} {bar=}'
    assert s.attributes[LEVEL_KEY] == 'info'
    assert s.attributes[LOG_TYPE_KEY] == 'log'


def test_log_with_tags(observe: Observe, exporter):
    observe.tags('tag1', 'tag2').info('test {name} {number}', name='foo', number=2)

    observe._client.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.attributes[MSG_TEMPLATE_KEY] == 'test {name} {number}'
    assert s.attributes[LOG_TYPE_KEY] == 'log'
    assert s.attributes['name'] == 'foo'
    assert s.attributes['number'] == 2
    assert s.attributes[TAGS_KEY] == ('tag1', 'tag2')


def test_log_with_multiple_tags(observe: Observe, exporter):
    observe_with_2_tags = observe.tags('tag1').tags('tag2')
    observe_with_2_tags.info('test {name} {number}', name='foo', number=2)
    observe._client.provider.force_flush()
    s = exporter.exported_spans[0]
    assert s.attributes[TAGS_KEY] == ('tag1', 'tag2')

    observe_with_4_tags = observe_with_2_tags.tags('tag3', 'tag4')
    observe_with_4_tags.info('test {name} {number}', name='foo', number=2)
    observe._client.provider.force_flush()
    s = exporter.exported_spans[0]
    assert s.attributes[TAGS_KEY] == ('tag1', 'tag2', 'tag3', 'tag4')


def test_instrument(observe: Observe, exporter):
    @observe.instrument('hello-world {a=}')
    def hello_world(a: int) -> str:
        return f'hello {a}'

    assert hello_world(123) == 'hello 123'

    observe._client.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.name == 'hello-world a=123'
    assert dict(s.attributes) == {
        'logfire.msg_template': 'hello-world {a=}',
        'logfire.log_type': 'start_span',
        'a': 123,
    }

    s = exporter.exported_spans[1]

    assert s.name.endswith('.hello_world')
    assert dict(s.attributes) == {'logfire.log_type': 'real_span'}


def test_instrument_extract_false(observe: Observe, exporter):
    @observe.instrument('hello-world', extract_args=False)
    def hello_world(a: int) -> str:
        return f'hello {a}'

    assert hello_world(123) == 'hello 123'

    observe._client.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.name == 'hello-world'
    assert dict(s.attributes) == {'logfire.msg_template': 'hello-world', 'logfire.log_type': 'start_span'}
