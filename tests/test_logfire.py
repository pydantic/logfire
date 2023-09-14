import json
from typing import cast

import pytest
from dirty_equals import IsPositive, IsStr
from opentelemetry.trace import format_span_id
from pydantic import BaseModel
from pydantic_core import ValidationError

from logfire import Observe, __version__
from logfire._observe import LEVEL_KEY, LOG_TYPE_KEY, MSG_TEMPLATE_KEY, NULL_ARGS_KEY, START_PARENT_ID, TAGS_KEY

from .conftest import TestExporter


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
def test_log(observe: Observe, exporter: TestExporter, level: str):
    getattr(observe, level)('test {name} {number} {none}', name='foo', number=2, none=None)

    observe._client.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.attributes[LEVEL_KEY] == level
    assert s.attributes[MSG_TEMPLATE_KEY] == 'test {name} {number} {none}'
    assert s.attributes[LOG_TYPE_KEY] == 'log'
    assert s.attributes['name'] == 'foo'
    assert s.attributes['number'] == 2
    assert s.attributes[NULL_ARGS_KEY] == ('none',)
    assert TAGS_KEY not in s.attributes


def test_log_equals(observe: Observe, exporter: TestExporter) -> None:
    observe.info('test message {foo=} {bar=}', foo='foo', bar=3)

    observe._client.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.name == 'test message foo=foo bar=3'
    assert s.attributes['foo'] == 'foo'
    assert s.attributes['bar'] == 3
    assert s.attributes[MSG_TEMPLATE_KEY] == 'test message {foo=} {bar=}'
    assert s.attributes[LEVEL_KEY] == 'info'
    assert s.attributes[LOG_TYPE_KEY] == 'log'


def test_log_with_tags(observe: Observe, exporter: TestExporter):
    observe.tags('tag1', 'tag2').info('test {name} {number}', name='foo', number=2)

    observe._client.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.attributes[MSG_TEMPLATE_KEY] == 'test {name} {number}'
    assert s.attributes[LOG_TYPE_KEY] == 'log'
    assert s.attributes['name'] == 'foo'
    assert s.attributes['number'] == 2
    assert s.attributes[TAGS_KEY] == ('tag1', 'tag2')


def test_log_with_multiple_tags(observe: Observe, exporter: TestExporter):
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


def test_instrument(observe: Observe, exporter: TestExporter):
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


def test_instrument_extract_false(observe: Observe, exporter: TestExporter):
    @observe.instrument('hello-world', extract_args=False)
    def hello_world(a: int) -> str:
        return f'hello {a}'

    assert hello_world(123) == 'hello 123'

    observe._client.provider.force_flush()
    s = exporter.exported_spans[0]

    assert s.name == 'hello-world'
    assert dict(s.attributes) == {'logfire.msg_template': 'hello-world', 'logfire.log_type': 'start_span'}


def test_validation_error_on_instrument(observe: Observe, exporter: TestExporter):
    class Model(BaseModel):
        a: int

    @observe.instrument('hello-world {a=}')
    def run(a: str) -> Model:
        return Model(a=a)  # type: ignore

    with pytest.raises(ValidationError):
        run('haha')

    observe._client.provider.force_flush()

    s = exporter.exported_spans.pop()
    assert len(s.events) == 1
    event = s.events[0]
    assert event.name == 'exception' and event.attributes
    assert event.attributes.get('exception.type') == 'ValidationError'
    assert '1 validation error for Model' in cast(str, event.attributes.get('exception.message'))
    assert event.attributes.get('exception.stacktrace') is not None

    data = json.loads(cast(bytes, event.attributes.get('exception.logfire.data')))
    # insert_assert(data)
    assert data == {
        'errors': [
            {
                'type': 'int_parsing',
                'loc': ['a'],
                'msg': 'Input should be a valid integer, unable to parse string as an integer',
                'input': 'haha',
            }
        ]
    }

    errors = json.loads(cast(bytes, event.attributes.get('exception.logfire.trace')))
    # insert_assert(errors)
    assert errors == {
        'stacks': [
            {
                'exc_type': 'ValidationError',
                'exc_value': "1 validation error for Model\na\n  Input should be a valid integer, unable to parse string as an integer [type=int_parsing, input_value='haha', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.3/v/int_parsing",
                'syntax_error': None,
                'is_cause': False,
                'frames': [
                    {
                        'filename': IsStr(regex=r'.*/logfire/_observe.py'),
                        'lineno': IsPositive(),
                        'name': 'record_exception',
                        'line': '',
                        'locals': None,
                    },
                    {
                        'filename': IsStr(regex=r'.*/logfire/_observe.py'),
                        'lineno': IsPositive(),
                        'name': 'wrapper',
                        'line': '',
                        'locals': None,
                    },
                    {
                        'filename': IsStr(regex=r'.*/tests/test_logfire.py'),
                        'lineno': IsPositive(),
                        'name': 'run',
                        'line': '',
                        'locals': None,
                    },
                    {
                        'filename': IsStr(regex=r'.*/pydantic/main.py'),
                        'lineno': IsPositive(),
                        'name': '__init__',
                        'line': '',
                        'locals': None,
                    },
                ],
            }
        ]
    }


def test_validation_error_on_span(observe: Observe, exporter: TestExporter) -> None:
    class Model(BaseModel):
        a: int

    def run(a: str) -> None:
        with observe.span('test span', 'test'):
            Model(a=a)  # type: ignore

    with pytest.raises(ValidationError):
        run('haha')

    observe._client.provider.force_flush()

    s = exporter.exported_spans.pop()
    assert len(s.events) == 1
    event = s.events[0]
    assert event.name == 'exception' and event.attributes
    assert event.attributes.get('exception.type') == 'ValidationError'
    assert '1 validation error for Model' in cast(str, event.attributes.get('exception.message'))
    assert event.attributes.get('exception.stacktrace') is not None

    data = json.loads(cast(bytes, event.attributes.get('exception.logfire.data')))
    # insert_assert(data)
    assert data == {
        'errors': [
            {
                'type': 'int_parsing',
                'loc': ['a'],
                'msg': 'Input should be a valid integer, unable to parse string as an integer',
                'input': 'haha',
            }
        ]
    }

    errors = json.loads(cast(bytes, event.attributes.get('exception.logfire.trace')))
    # insert_assert(errors)
    assert errors == {
        'stacks': [
            {
                'exc_type': 'ValidationError',
                'exc_value': "1 validation error for Model\na\n  Input should be a valid integer, unable to parse string as an integer [type=int_parsing, input_value='haha', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.3/v/int_parsing",
                'syntax_error': None,
                'is_cause': False,
                'frames': [
                    {
                        'filename': IsStr(regex=r'.*/logfire/_observe.py'),
                        'lineno': IsPositive(),
                        'name': 'record_exception',
                        'line': '',
                        'locals': None,
                    },
                    {
                        'filename': IsStr(regex=r'.*/logfire/_observe.py'),
                        'lineno': IsPositive(),
                        'name': 'span',
                        'line': '',
                        'locals': None,
                    },
                    {
                        'filename': IsStr(regex=r'.*/tests/test_logfire.py'),
                        'lineno': IsPositive(),
                        'name': 'run',
                        'line': '',
                        'locals': None,
                    },
                    {
                        'filename': IsStr(regex=r'.*/pydantic/main.py'),
                        'lineno': IsPositive(),
                        'name': '__init__',
                        'line': '',
                        'locals': None,
                    },
                ],
            }
        ]
    }
