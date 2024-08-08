from __future__ import annotations

import os
import sys
from typing import Any

import pytest
from dirty_equals import IsJson, IsPartialDict
from inline_snapshot import snapshot
from opentelemetry.sdk.environment_variables import OTEL_RESOURCE_ATTRIBUTES
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace.propagation import get_current_span

import logfire
from logfire._internal.scrubbing import NoopScrubber
from logfire.testing import IncrementalIdGenerator, TestExporter, TimeGenerator


def test_scrub_attribute(exporter: TestExporter):
    logfire.info(
        'Password: {user_password}',
        user_password=['hunter2'],
        mode='password',
        modes='passwords',
        Author='Alice1',
        authors='Alice2',
        authr='Alice3',
        authorization='Alice4',
    )
    # We redact:
    # - The `user_password` attribute.
    # - The `modes` attribute.
    # - `authr` and `authorization` because they contain 'auth' but don't look like 'author(s)'.
    # Things intentionally not redacted even though they contain "password":
    # - The `mode` attribute, because the value 'password' is a full match.
    # - 'Author' and 'authors': special cases in the regex that looks for 'auth'.
    # - logfire.msg_template
    # - The span name, which is the same as msg_template and shouldn't contain data.
    # - logfire.json_schema
    # - code.filepath (contains 'secret' - this test filename is itself part of the test)
    # - logfire.msg: while `{user_password}` is obviously sensitive, the user clearly explicitly wanted it to be logged.
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Password: {user_password}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'Password: {user_password}',
                    'logfire.msg': "Password: ['hunter2']",
                    'code.filepath': 'test_secret_scrubbing.py',
                    'code.function': 'test_scrub_attribute',
                    'code.lineno': 123,
                    'user_password': "[Scrubbed due to 'password']",
                    'mode': 'password',
                    'modes': "[Scrubbed due to 'password']",
                    'Author': 'Alice1',
                    'authors': 'Alice2',
                    'authr': "[Scrubbed due to 'auth']",
                    'authorization': "[Scrubbed due to 'auth']",
                    'logfire.json_schema': '{"type":"object","properties":{"user_password":{"type":"array"},"mode":{},"modes":{},"Author":{},"authors":{},"authr":{},"authorization":{}}}',
                    'logfire.scrubbed': IsJson(
                        [
                            {'path': ['attributes', 'user_password'], 'matched_substring': 'password'},
                            {'path': ['attributes', 'modes'], 'matched_substring': 'password'},
                            {'path': ['attributes', 'authr'], 'matched_substring': 'auth'},
                            {'path': ['attributes', 'authorization'], 'matched_substring': 'auth'},
                        ]
                    ),
                },
            }
        ]
    )


def test_scrub_message(exporter: TestExporter):
    logfire.info('User: {user}', user=[{'name': 'John', 'password': 'hunter2'}])
    # Only the sensitive part of the `user` attribute is redacted.
    # The full formatted value is redacted from the message,
    # because the formatting code only sees the full `str(user)`.
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'User: {user}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'User: {user}',
                    'logfire.msg': "User: [Scrubbed due to 'password']",
                    'code.filepath': 'test_secret_scrubbing.py',
                    'code.function': 'test_scrub_message',
                    'code.lineno': 123,
                    'user': '[{"name": "John", "password": "[Scrubbed due to \'password\']"}]',
                    'logfire.scrubbed': IsJson(
                        [
                            {'path': ['message', 'user'], 'matched_substring': 'password'},
                            {'path': ['attributes', 'user', 0, 'password'], 'matched_substring': 'password'},
                        ]
                    ),
                    'logfire.json_schema': '{"type":"object","properties":{"user":{"type":"array"}}}',
                },
            }
        ]
    )


class PasswordError(Exception):
    pass


def test_scrub_events(exporter: TestExporter):
    def get_password():
        with logfire.span('get_password'):
            get_current_span().add_event('password', {'password': 'hunter2', 'other': 'safe'})
            try:
                raise PasswordError('Password: hunter2')
            except Exception as e:
                get_current_span().record_exception(e, attributes={'exception.stacktrace': 'wrong and secret'})
                raise

    with pytest.raises(PasswordError):
        get_password()

    # We redact:
    # - The `password` event attribute.
    # - The `exception.message` event attribute
    # - The full `exception.stacktrace` event attribute in the second event, i.e. 'wrong and secret'.
    # - The part of the `exception.stacktrace` event attribute in the third event that's the exception message.
    # We don't redact (despite containing "password"):
    # - The event name.
    # - The exception type.
    # - Most of the `exception.stacktrace` event attribute in the third event.
    #     (although it's mostly been normalized away by the test exporter)
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'get_password',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_secret_scrubbing.py',
                    'code.function': 'get_password',
                    'code.lineno': 123,
                    'logfire.msg_template': 'get_password',
                    'logfire.msg': 'get_password',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.scrubbed': IsJson(
                        [
                            {
                                'path': ['otel_events', 0, 'attributes', 'password'],
                                'matched_substring': 'password',
                            },
                            {
                                'path': ['otel_events', 1, 'attributes', 'exception.message'],
                                'matched_substring': 'Password',
                            },
                            {
                                'path': ['otel_events', 1, 'attributes', 'exception.stacktrace'],
                                'matched_substring': 'secret',
                            },
                            {
                                'path': ['otel_events', 2, 'attributes', 'exception.message'],
                                'matched_substring': 'Password',
                            },
                        ]
                    ),
                },
                'events': [
                    {
                        'name': 'password',
                        'timestamp': 2000000000,
                        'attributes': {
                            'password': "[Scrubbed due to 'password']",
                            'other': 'safe',
                        },
                    },
                    {
                        'name': 'exception',
                        'timestamp': 3000000000,
                        'attributes': {
                            'exception.type': 'tests.test_secret_scrubbing.PasswordError',
                            'exception.message': "[Scrubbed due to 'Password']",
                            'exception.stacktrace': "[Scrubbed due to 'secret']",
                            'exception.escaped': 'False',
                        },
                    },
                    {
                        'name': 'exception',
                        'timestamp': 4000000000,
                        'attributes': {
                            'exception.type': 'tests.test_secret_scrubbing.PasswordError',
                            'exception.message': "[Scrubbed due to 'Password']",
                            'exception.stacktrace': (
                                "tests.test_secret_scrubbing.PasswordError: [Scrubbed due to 'Password']"
                            ),
                            'exception.escaped': 'True',
                        },
                    },
                ],
            }
        ]
    )


def test_scrubbing_config(exporter: TestExporter, id_generator: IncrementalIdGenerator, time_generator: TimeGenerator):
    def callback(match: logfire.ScrubMatch):
        if match.path[-1] == 'my_password':
            return str(match)
        elif match.path[-1] == 'bad_value':
            # This is not a valid OTEL attribute value, so it will be removed completely.
            return match

    logfire.configure(
        scrubbing=logfire.ScrubbingOptions(
            extra_patterns=['my_pattern'],
            callback=callback,
        ),
        send_to_logfire=False,
        console=False,
        id_generator=id_generator,
        ns_timestamp_generator=time_generator,
        additional_span_processors=[SimpleSpanProcessor(exporter)],
    )

    # Note the values (or lack thereof) of each of these attributes in the exported span.
    logfire.info('hi', my_password='hunter2', other='matches_my_pattern', bad_value='the_password')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'code.filepath': 'test_secret_scrubbing.py',
                    'code.function': 'test_scrubbing_config',
                    'code.lineno': 123,
                    'my_password': (
                        'ScrubMatch('
                        "path=('attributes', 'my_password'), "
                        "value='hunter2', "
                        "pattern_match=<re.Match object; span=(3, 11), match='password'>"
                        ')'
                    ),
                    'other': "[Scrubbed due to 'my_pattern']",
                    'logfire.json_schema': '{"type":"object","properties":{"my_password":{},"other":{},"bad_value":{}}}',
                    'logfire.scrubbed': '[{"path": ["attributes", "other"], "matched_substring": "my_pattern"}]',
                },
            }
        ]
    )


def test_dont_scrub_resource(
    exporter: TestExporter, id_generator: IncrementalIdGenerator, time_generator: TimeGenerator
):
    os.environ[OTEL_RESOURCE_ATTRIBUTES] = 'my_password=hunter2,yours=your_password,other=safe=good'
    logfire.configure(
        send_to_logfire=False,
        console=False,
        id_generator=id_generator,
        ns_timestamp_generator=time_generator,
        additional_span_processors=[SimpleSpanProcessor(exporter)],
    )
    logfire.info('hi')
    assert dict(exporter.exported_spans[0].resource.attributes) == IsPartialDict(
        {
            'telemetry.sdk.language': 'python',
            'telemetry.sdk.name': 'opentelemetry',
            'my_password': 'hunter2',
            'yours': 'your_password',
            'other': 'safe=good',
        }
    )


def test_disable_scrubbing(exporter: TestExporter, config_kwargs: dict[str, Any]):
    logfire.configure(**config_kwargs, scrubbing=False)

    config = logfire.DEFAULT_LOGFIRE_INSTANCE.config
    assert config.scrubbing is False
    assert isinstance(config.scrubber, NoopScrubber)

    logfire.info('Password: {user_password}', user_password='my secret password')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Password: {user_password}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'Password: {user_password}',
                    'logfire.msg': 'Password: my secret password',
                    'code.filepath': 'test_secret_scrubbing.py',
                    'code.function': 'test_disable_scrubbing',
                    'code.lineno': 123,
                    'user_password': 'my secret password',
                    'logfire.json_schema': '{"type":"object","properties":{"user_password":{}}}',
                },
            }
        ]
    )


def test_scrubbing_deprecated_args(config_kwargs: dict[str, Any]):
    def callback(match: logfire.ScrubMatch):  # pragma: no cover
        return str(match)

    with pytest.warns(
        DeprecationWarning, match='The `scrubbing_callback` and `scrubbing_patterns` arguments are deprecated.'
    ):
        logfire.configure(**config_kwargs, scrubbing_patterns=['my_pattern'], scrubbing_callback=callback)

    config = logfire.DEFAULT_LOGFIRE_INSTANCE.config
    assert config.scrubbing
    assert config.scrubbing.extra_patterns == ['my_pattern']
    assert config.scrubbing.callback is callback


def test_scrubbing_deprecated_args_combined_with_new_options():
    with pytest.raises(
        ValueError,
        match='Cannot specify `scrubbing` and `scrubbing_callback` or `scrubbing_patterns` at the same time.',
    ):
        logfire.configure(scrubbing_patterns=['my_pattern'], scrubbing=logfire.ScrubbingOptions())


@pytest.mark.skipif(sys.version_info[:2] < (3, 9), reason='f-string magic is not allowed in 3.8')
def test_fstring_magic_scrubbing(exporter: TestExporter):
    password = 'secret-password'
    name = 'John'
    logfire.info(f'User: {name}, password: {password}', foo=1234)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'User: {name}, password: {password}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'User: {name}, password: {password}',
                    'logfire.msg': "User: John, password: [Scrubbed due to 'secret']",
                    'code.filepath': 'test_secret_scrubbing.py',
                    'code.function': 'test_fstring_magic_scrubbing',
                    'code.lineno': 123,
                    'foo': 1234,
                    'name': 'John',
                    'password': "[Scrubbed due to 'password']",
                    'logfire.json_schema': '{"type":"object","properties":{"foo":{},"name":{},"password":{}}}',
                    'logfire.scrubbed': IsJson(
                        [
                            {'path': ['message', 'password'], 'matched_substring': 'secret'},
                            {'path': ['attributes', 'password'], 'matched_substring': 'password'},
                        ]
                    ),
                },
            }
        ]
    )
