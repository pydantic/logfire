from __future__ import annotations

import json
import re
from io import StringIO
from pathlib import Path
from threading import Event, get_ident
from typing import Any

import pytest
from dirty_equals import IsJson, IsPartialDict
from inline_snapshot import snapshot
from opentelemetry._logs import LogRecord, get_logger
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.environment_variables import OTEL_RESOURCE_ATTRIBUTES
from opentelemetry.sdk.trace import ConcurrentMultiSpanProcessor, ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.trace.propagation import get_current_span

import logfire
from logfire._internal.exporters.processor_wrapper import SpanProcessorGroup
from logfire._internal.scrubbing import DEFAULT_PATTERNS, NoopScrubber, Scrubber
from logfire.sampling import TailSamplingSpanInfo
from logfire.testing import TestExporter, TestLogExporter


def test_span_processor_group_flushes_after_failure():
    flushed: list[bool] = []

    class FlushProcessor(SpanProcessor):
        def __init__(self, result: bool):
            self.result = result

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            flushed.append(self.result)
            return self.result

    group = SpanProcessorGroup()
    group.add_span_processor(FlushProcessor(False))
    group.add_span_processor(FlushProcessor(True))

    assert not group.force_flush(timeout_millis=0)
    assert flushed == []
    assert not group.force_flush()
    assert flushed == [False, True]


@pytest.mark.parametrize('include_attributes', [False, True])
@pytest.mark.parametrize('concurrent', [False, True])
def test_scrubbing_thread_depends_on_console_attributes(
    config_kwargs: dict[str, Any], include_attributes: bool, concurrent: bool, monkeypatch: pytest.MonkeyPatch
):
    from opentelemetry.context import Context

    caller = get_ident()
    scrubbed = Event()
    threads: list[int] = []

    class StartProcessor(SpanProcessor):
        def on_start(self, span: Span, parent_context: Context | None = None) -> None:
            assert get_ident() == caller
            span.set_attribute('password', 'sensitive')

    # OTel 1.39's default implementation returns None for start-only processors.
    def noop_force_flush(processor: StartProcessor, timeout_millis: int) -> None:
        pass

    monkeypatch.setattr(StartProcessor, 'force_flush', noop_force_flush)

    def callback(match: logfire.ScrubMatch) -> str:
        threads.append(get_ident())
        scrubbed.set()
        return '[masked]'

    exporters = [TestExporter(), TestExporter()]
    processors: list[SpanProcessor] = [BatchSpanProcessor(e) for e in exporters]
    if concurrent:
        group = ConcurrentMultiSpanProcessor()
        for processor in processors:
            group.add_span_processor(processor)
        processors = [group]
    output = StringIO()
    config_kwargs.update(
        additional_span_processors=[StartProcessor(), *processors],
        console=logfire.ConsoleOptions(verbose=False, include_attributes=include_attributes, output=output),
        scrubbing=logfire.ScrubbingOptions(callback=callback),
    )
    logfire.configure(**config_kwargs)
    logfire.info('test record', password='initial')

    assert scrubbed.wait(timeout=5)
    assert logfire.force_flush()
    assert len(threads) == 1
    assert (threads[0] == caller) is include_attributes
    assert 'test record' in output.getvalue()
    assert ('[masked]' in output.getvalue()) is include_attributes
    for exporter in exporters:
        (span,) = exporter.exported_spans
        assert span.attributes is not None
        assert span.attributes['password'] == '[masked]'


@pytest.mark.parametrize('tail_sampling', [False, True])
def test_background_scrubbing_flushes_pending_and_completed_spans(config_kwargs: dict[str, Any], tail_sampling: bool):
    exporter = TestExporter()
    config_kwargs['additional_span_processors'] = [BatchSpanProcessor(exporter, schedule_delay_millis=60_000)]
    sampling = logfire.SamplingOptions(tail=lambda _: 1.0) if tail_sampling else None
    logfire.configure(**config_kwargs, sampling=sampling)

    with logfire.span('test span', password='sensitive'):
        assert logfire.force_flush()
        (pending,) = exporter.exported_spans
        assert pending.attributes is not None
        assert pending.attributes['logfire.span_type'] == 'pending_span'
        assert pending.attributes['password'] == "[Scrubbed due to 'password']"

    logfire.shutdown()
    _, completed = exporter.exported_spans
    assert completed.attributes is not None
    assert completed.attributes['logfire.span_type'] == 'span'
    assert completed.attributes['password'] == "[Scrubbed due to 'password']"


@pytest.mark.parametrize('concurrent', [False, True])
def test_custom_end_processor_keeps_scrubbing_synchronous(config_kwargs: dict[str, Any], concurrent: bool):
    caller = get_ident()
    exporter = TestExporter()
    synchronous: SpanProcessor = SimpleSpanProcessor(exporter)
    if concurrent:
        group = ConcurrentMultiSpanProcessor()
        group.add_span_processor(synchronous)
        synchronous = group
    threads: list[int] = []

    def callback(match: logfire.ScrubMatch) -> None:
        threads.append(get_ident())

    config_kwargs['additional_span_processors'] = [BatchSpanProcessor(TestExporter()), synchronous]
    logfire.configure(**config_kwargs, scrubbing=logfire.ScrubbingOptions(callback=callback))
    logfire.info('test record', password='sensitive')

    assert threads == [caller]
    (span,) = exporter.exported_spans
    assert span.attributes is not None
    assert span.attributes['password'] == "[Scrubbed due to 'password']"


def test_scrubbing_after_tail_sampling(config_kwargs: dict[str, Any]):
    exported: list[ReadableSpan] = []
    scrubbed_values: list[Any] = []

    class DeferredProcessor(SpanProcessor):
        tail_sampling_defer_on_start = True

        def on_end(self, span: ReadableSpan) -> None:
            exported.append(span)

    def sample(info: TailSamplingSpanInfo) -> float:
        if info.event == 'end' and info.span.attributes and info.span.attributes.get('password') == 'keep':
            return 1.0
        return 0.0

    def callback(match: logfire.ScrubMatch) -> None:
        scrubbed_values.append(match.value)

    config_kwargs['additional_span_processors'].append(DeferredProcessor())
    logfire.configure(
        **config_kwargs,
        sampling=logfire.SamplingOptions(tail=sample),
        scrubbing=logfire.ScrubbingOptions(callback=callback),
    )
    logfire.info('discarded', password='discard')
    logfire.info('kept', password='keep')

    assert scrubbed_values == ['keep']
    (span,) = exported
    assert span.attributes is not None
    assert span.attributes['password'] == "[Scrubbed due to 'password']"


DEFAULT_PATTERN_EXAMPLES = {
    'password': 'has_password_value',
    'passwd': 'has_passwd_value',
    'mysql_pwd': 'has_mysql_pwd_value',
    'secret': 'has_secret_value',
    r'auth(?!ors?\b)': 'has_authorization_value',
    'credential': 'has_credential_value',
    'private[._ -]?key': 'has_private-key_value',
    'passphrase': 'has_passphrase_value',
    '(?:signing|hmac)[._ -]?key': 'has_signing_key_value',
    'api[._ -]?key': 'has_api.key_value',
    'session': 'has_session_value',
    'cookie': 'has_cookie_value',
    'social[._ -]?security': 'has_social security_value',
    'credit[._ -]?card': 'has_credit_card_value',
    'logfire[._ -]?token': 'has_logfire-token_value',
    r'(?:access|refresh|bearer|(?:\b|_)id)[._ -]?token': 'has_access_token_value',
    'security[._ -]?token': 'has_security_token_value',
    r'pylf_v\d+_': 'has_pylf_v12_token',
    r'(?:\b|_)csrf(?:\b|_)': 'has csrf value',
    r'(?:\b|_)xsrf(?:\b|_)': 'has xsrf value',
    r'(?:\b|_)jwt(?:\b|_)': 'has jwt value',
    r'(?:\b|_)ssn(?:\b|_)': 'has ssn value',
}


def test_optimized_default_patterns_match_naive_pattern():
    """The optimized prefilter must not change which default pattern matches first."""
    assert DEFAULT_PATTERN_EXAMPLES.keys() == set(DEFAULT_PATTERNS)
    naive_pattern = re.compile('|'.join(DEFAULT_PATTERNS), re.IGNORECASE | re.DOTALL)

    for value in [*DEFAULT_PATTERN_EXAMPLES.values(), 'has \u017fecret value', 'has credent\u0131al value']:
        expected = naive_pattern.search(value)
        assert expected is not None

        scrub_matches: list[logfire.ScrubMatch] = []

        def callback(match: logfire.ScrubMatch):
            scrub_matches.append(match)
            return match.value

        result, scrubbed_notes = Scrubber(None, callback).scrub_value(('attributes', 'value'), value)

        assert result == value
        assert scrubbed_notes == []
        assert len(scrub_matches) == 1
        actual = scrub_matches[0].pattern_match
        assert (actual.span(), actual.group(0)) == (expected.span(), expected.group(0))


@pytest.mark.parametrize(
    ('extra_pattern', 'value', 'expected_match'),
    [
        ('custom', 'custom before password', 'custom'),
        ('pass', 'passwords', 'password'),
        (r'\d+', '123 before password', '123'),
    ],
)
def test_optimized_default_patterns_preserve_extra_pattern_order(extra_pattern: str, value: str, expected_match: str):
    matches: list[str] = []

    def callback(match: logfire.ScrubMatch):
        matches.append(match.pattern_match.group(0))
        return match.value

    result, scrubbed_notes = Scrubber([extra_pattern], callback).scrub_value(('attributes', 'value'), value)

    assert result == value
    assert scrubbed_notes == []
    assert matches[0] == expected_match


def test_callback_whitelists_string_match_but_scrubs_later_value_match():
    matches: list[str] = []

    def callback(match: logfire.ScrubMatch):
        matched = match.pattern_match.group(0)
        matches.append(matched)
        if matched == 'password':
            return match.value

    result, notes = Scrubber(None, callback).scrub_value(('attributes', 'value'), 'password allowed; secret=hunter2')

    assert result == "[Scrubbed due to 'secret']"
    assert matches == ['password', 'secret']
    assert notes == [{'path': ('attributes', 'value'), 'matched_substring': 'secret'}]


def test_callback_whitelists_key_match_but_scrubs_later_key_match():
    def callback(match: logfire.ScrubMatch):
        if match.pattern_match.group(0) == 'password':
            return match.value

    result, notes = Scrubber(None, callback).scrub_value(('attributes',), {'password_secret': 'hunter2'})

    assert result == {'password_secret': "[Scrubbed due to 'secret']"}
    assert notes == [{'path': ('attributes', 'password_secret'), 'matched_substring': 'secret'}]


def test_callback_whitelists_key_with_scalar_value_but_scrubs_later_key_match():
    def callback(match: logfire.ScrubMatch):
        if match.pattern_match.group(0) == 'password':
            return match.value

    result, notes = Scrubber(None, callback).scrub_value(('attributes',), {'password_secret': 1234})

    assert result == {'password_secret': "[Scrubbed due to 'secret']"}
    assert notes == [{'path': ('attributes', 'password_secret'), 'matched_substring': 'secret'}]


def test_callback_equal_value_with_different_type_is_final():
    def callback(match: logfire.ScrubMatch):
        return True

    result, notes = Scrubber(None, callback).scrub_value(('attributes',), {'password_secret': 1})

    assert result == {'password_secret': True}
    assert notes == []


@pytest.mark.parametrize(
    'value', [b'password=hunter2', bytearray(b'password=hunter2'), memoryview(b'password=hunter2')]
)
def test_callback_whitelisted_key_scrubs_binary_value(value: bytes | bytearray | memoryview):
    def callback(match: logfire.ScrubMatch):
        if match.pattern_match.string == 'password_hint':
            return match.value

    result, notes = Scrubber(None, callback).scrub_value(('attributes',), {'password_hint': value})

    assert result == {'password_hint': "[Scrubbed due to 'password']"}
    assert notes == [{'path': ('attributes', 'password_hint'), 'matched_substring': 'password'}]


def test_callback_whitelists_key_but_scrubs_string_value():
    def callback(match: logfire.ScrubMatch):
        if match.pattern_match.string == 'password_hint':
            return match.value

    result, notes = Scrubber(None, callback).scrub_value(('attributes',), {'password_hint': 'secret=hunter2'})

    assert result == {'password_hint': "[Scrubbed due to 'secret']"}
    assert notes == [{'path': ('attributes', 'password_hint'), 'matched_substring': 'secret'}]


def test_callback_receives_scrubbed_string_before_key_match():
    def callback(match: logfire.ScrubMatch):
        if match.pattern_match.string == 'password_hint':
            assert match.value == "[Scrubbed due to 'secret']"
            return match.value

    result, notes = Scrubber(None, callback).scrub_value(('attributes',), {'password_hint': 'secret=hunter2'})

    assert result == {'password_hint': "[Scrubbed due to 'secret']"}
    assert notes == [{'path': ('attributes', 'password_hint'), 'matched_substring': 'secret'}]


def test_callback_whitelists_overlapping_later_start():
    matches: list[str] = []

    def callback(match: logfire.ScrubMatch):
        matched = match.pattern_match.group(0)
        matches.append(matched)
        if matched != 'secret':
            return match.value

    result, notes = Scrubber(['assword'], callback).scrub_value(('attributes', 'value'), 'password secret=hunter2')

    assert result == "[Scrubbed due to 'secret']"
    assert matches == ['password', 'assword', 'secret']
    assert notes == [{'path': ('attributes', 'value'), 'matched_substring': 'secret'}]


def test_callback_whitelists_zero_width_match_at_end():
    matches: list[tuple[int, int]] = []

    def callback(match: logfire.ScrubMatch):
        matches.append(match.pattern_match.span())
        return match.value

    result, notes = Scrubber(['$'], callback).scrub_value(('attributes', 'value'), 'plain')

    assert result == 'plain'
    assert notes == []
    assert matches == [(5, 5)]


def test_callback_whitelists_zero_width_match_before_later_secret():
    def callback(match: logfire.ScrubMatch):
        if match.pattern_match.group(0) == '':
            return match.value

    result, notes = Scrubber([r'(?=x)'], callback).scrub_value(('attributes', 'value'), 'x secret=hunter2')

    assert result == "[Scrubbed due to 'secret']"
    assert notes == [{'path': ('attributes', 'value'), 'matched_substring': 'secret'}]


def test_callback_whitelists_zero_width_key_match_at_end():
    result, notes = Scrubber(['$'], lambda match: match.value).scrub_value(('attributes',), {'plain': 'value'})

    assert result == {'plain': 'value'}
    assert notes == []


def test_callback_changed_string_is_final():
    def callback(match: logfire.ScrubMatch):
        return 'replacement secret=visible'

    result, notes = Scrubber(None, callback).scrub_value(('attributes', 'value'), 'password and secret=hunter2')

    assert result == 'replacement secret=visible'
    assert notes == []


@pytest.mark.parametrize('in_key', [False, True])
def test_callback_allowed_matches_have_a_limit(in_key: bool):
    value = '1' * 40_000 + ' suffix'
    data = {value: 'plain'} if in_key else {'plain': value}

    result, notes = Scrubber([r'\d+'], lambda match: match.value).scrub_value(('attributes',), data)

    assert result == {value if in_key else 'plain': '[Scrubbed due to too many allowed matches]'}
    assert notes == []


def test_callback_equal_string_copy_does_not_rewrite_json():
    def callback(match: logfire.ScrubMatch):
        if match.path == ('attributes', 'data', 'password_hint'):
            return (' ' + match.value)[1:]

    original = '{"password_hint":"allowed","amount":1e400}'
    assert Scrubber(None, callback).scrub_value(('attributes', 'data'), original) == (original, [])


def test_default_pattern_start_chars_cover_each_pattern():
    """The prefilter must still find each default pattern's own first match.

    Compare against that pattern in isolation, not the combined leftmost match,
    so a new pattern cannot be silently disabled if its example also contains
    an earlier default match, e.g. adding `token` with `has_secret_token_value`.
    """
    assert DEFAULT_PATTERN_EXAMPLES.keys() == set(DEFAULT_PATTERNS)
    isolated_examples = [
        *DEFAULT_PATTERN_EXAMPLES.items(),
        (r'(?:\b|_)csrf(?:\b|_)', 'has_csrf_value'),
        (r'(?:\b|_)xsrf(?:\b|_)', 'has_xsrf_value'),
        (r'(?:\b|_)jwt(?:\b|_)', 'has_jwt_value'),
        (r'(?:\b|_)ssn(?:\b|_)', 'has_ssn_value'),
        (r'(?:access|refresh|bearer|(?:\b|_)id)[._ -]?token', 'has refresh-token value'),
        (r'(?:access|refresh|bearer|(?:\b|_)id)[._ -]?token', 'has bearer token value'),
        (r'(?:access|refresh|bearer|(?:\b|_)id)[._ -]?token', 'has_id_token_value'),
        (r'(?:access|refresh|bearer|(?:\b|_)id)[._ -]?token', 'has idtoken value'),
        (r'(?:access|refresh|bearer|(?:\b|_)id)[._ -]?token', 'has access.token value'),
        ('(?:signing|hmac)[._ -]?key', 'has hmac-key value'),
        ('security[._ -]?token', 'has x-amz-security-token value'),
        ('secret', 'has \u017fecret value'),
        ('credential', 'has credent\u0131al value'),
    ]

    def make_callback(bucket: list[logfire.ScrubMatch]):
        def callback(match: logfire.ScrubMatch):
            bucket.append(match)
            return match.value

        return callback

    for pattern, value in isolated_examples:
        expected = re.compile(pattern, re.IGNORECASE | re.DOTALL).search(value)
        assert expected is not None, pattern

        scrub_matches: list[logfire.ScrubMatch] = []
        result, scrubbed_notes = Scrubber(None, make_callback(scrub_matches)).scrub_value(
            ('attributes', 'value'), value
        )

        assert result == value
        assert scrubbed_notes == []
        assert len(scrub_matches) == 1, (pattern, value)
        actual = scrub_matches[0].pattern_match
        assert (actual.span(), actual.group(0)) == (expected.span(), expected.group(0))


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


def test_scrub_log_event_attribute(logs_exporter: TestLogExporter):
    get_logger(__name__).emit(
        LogRecord(
            attributes={
                'event.name': 'Password: {user_password}',
                'user_password': ['hunter2'],
                'mode': 'password',
                'modes': 'passwords',
                'Author': 'Alice1',
                'authors': 'Alice2',
                'authr': 'Alice3',
                'authorization': 'Alice4',
            },
        )
    )
    # We redact:
    # - The `user_password` attribute.
    # - The `modes` attribute.
    # - `authr` and `authorization` because they contain 'auth' but don't look like 'author(s)'.
    # Things intentionally not redacted even though they contain "password":
    # - The `mode` attribute, because the value 'password' is a full match.
    # - 'Author' and 'authors': special cases in the regex that looks for 'auth'.
    # - event.name
    assert logs_exporter.exported_logs_as_dicts() == snapshot(
        [
            {
                'body': None,
                'severity_number': None,
                'severity_text': None,
                'attributes': {
                    'user_password': ("[Scrubbed due to 'password']",),
                    'mode': 'password',
                    'modes': "[Scrubbed due to 'password']",
                    'Author': 'Alice1',
                    'authors': 'Alice2',
                    'authr': "[Scrubbed due to 'auth']",
                    'authorization': "[Scrubbed due to 'auth']",
                    'event.name': 'Password: {user_password}',
                    'logfire.scrubbed': IsJson(
                        snapshot(
                            [
                                {'path': ['attributes', 'user_password'], 'matched_substring': 'password'},
                                {'path': ['attributes', 'modes'], 'matched_substring': 'password'},
                                {'path': ['attributes', 'authr'], 'matched_substring': 'auth'},
                                {'path': ['attributes', 'authorization'], 'matched_substring': 'auth'},
                            ]
                        )
                    ),
                },
                'timestamp': 1000000000,
                'observed_timestamp': 2000000000,
                'trace_id': 0,
                'span_id': 0,
                'trace_flags': 0,
            }
        ]
    )


def test_scrub_message(exporter: TestExporter):
    logfire.info('User: {user}', user=[{'name': 'John', 'password': 'hunter2'}])
    # Only the sensitive part of the `user` attribute is redacted.
    # The full formatted value is redacted from the message,
    # because the formatting code only sees the full `str(user)`.
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
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
                    'user': [{'name': 'John', 'password': "[Scrubbed due to 'password']"}],
                    'logfire.scrubbed': [
                        {'path': ['message', 'user'], 'matched_substring': 'password'},
                        {'path': ['attributes', 'user', 0, 'password'], 'matched_substring': 'password'},
                    ],
                    'logfire.json_schema': {'type': 'object', 'properties': {'user': {'type': 'array'}}},
                },
            }
        ]
    )


@pytest.mark.parametrize(
    ('value', 'expected', 'expected_notes'),
    [
        pytest.param(b'\x00\x01ab', b'\x00\x01ab', [], id='plain'),
        pytest.param(b'password=hunter2', "[Scrubbed due to 'password']", ['password'], id='secret'),
        pytest.param(b'\x00\xff\xfe', b'\x00\xff\xfe', [], id='not-utf8'),
    ],
)
def test_scrub_binary_values(value: bytes, expected: bytes | str, expected_notes: list[str]):
    """Binary values stay binary, and text hidden in them is still scrubbed."""
    result, scrubbed_notes = Scrubber(None).scrub_value(('attributes', 'payload'), value)

    assert result == expected
    assert [note['matched_substring'] for note in scrubbed_notes] == expected_notes


@pytest.mark.parametrize('error_type', [ValueError, RecursionError])
def test_scrub_json_that_cannot_be_parsed(monkeypatch: pytest.MonkeyPatch, error_type: type[Exception]):
    """A parse error must redact the text instead of aborting scrubbing of the whole span."""

    def raise_decode_error(*args: Any, **kwargs: Any):
        raise error_type('cannot decode JSON')

    monkeypatch.setattr(json, 'loads', raise_decode_error)

    result, scrubbed_notes = Scrubber(None).scrub_value(('attributes', 'payload'), b'["password"]')

    assert result == "[Scrubbed due to 'password']"
    assert [note['matched_substring'] for note in scrubbed_notes] == ['password']


def test_scrub_json_that_cannot_be_written_back(monkeypatch: pytest.MonkeyPatch):
    """A value that parses but cannot be walked or serialised is redacted as plain text."""

    def raise_recursion_error(*args: Any, **kwargs: Any):
        raise RecursionError('maximum recursion depth exceeded')

    monkeypatch.setattr(json, 'dumps', raise_recursion_error)

    result, scrubbed_notes = Scrubber(None).scrub_value(('attributes', 'payload'), b'["password=hunter2"]')

    assert result == "[Scrubbed due to 'password']"
    assert scrubbed_notes == snapshot(
        [
            {'path': ('attributes', 'payload', 0), 'matched_substring': 'password'},
            {'path': ('attributes', 'payload'), 'matched_substring': 'password'},
        ]
    )


def test_scrub_json_containers_without_a_raw_pattern_match(exporter: TestExporter):
    logfire.info('Example', data=r'{"pass\u0077ord":"hunter2"}', unchanged='{"amount":1e400}')

    (span,) = exporter.exported_spans_as_dict()
    assert json.loads(span['attributes']['data']) == {'password': "[Scrubbed due to 'password']"}
    assert span['attributes']['unchanged'] == '{"amount":1e400}'


def test_internal_exception_in_scrubbing_callback_does_not_export_secrets(
    exporter: TestExporter, config_kwargs: dict[str, Any], caplog: pytest.LogCaptureFixture
):
    def callback(match: logfire.ScrubMatch):
        if match.path == ('attributes', 'password'):
            raise RuntimeError('key callback failed')
        if match.path == ('attributes', 'data', 'password'):
            raise ValueError('JSON callback failed')

    logfire.configure(**config_kwargs, scrubbing=logfire.ScrubbingOptions(callback=callback))
    logfire.info('Example', password='hunter2', data=r'{"pass\u0077ord":"hunter2"}', other='secret=hunter2')

    (span,) = exporter.exported_spans_as_dict()
    attributes = span['attributes']
    assert attributes['password'] == "[Scrubbed due to 'password']"
    assert json.loads(attributes['data']) == {'password': "[Scrubbed due to 'password']"}
    assert attributes['other'] == "[Scrubbed due to 'secret']"
    assert [record.exc_info[0] for record in caplog.records if record.exc_info] == [RuntimeError, ValueError]


@pytest.mark.parametrize('copy_container', [False, True])
@pytest.mark.parametrize('container', [{'password': 'hunter2'}, [{'password': 'hunter2'}]])
def test_callback_whitelists_container_key_but_scrubs_contents(container: Any, copy_container: bool):
    def callback(match: logfire.ScrubMatch):
        if match.path == ('attributes', 'password_hint'):
            return match.value.copy() if copy_container else match.value

    result, notes = Scrubber(None, callback).scrub_value(('attributes',), {'password_hint': container})

    expected = {'password': "[Scrubbed due to 'password']"}
    assert result == {'password_hint': [expected] if isinstance(container, list) else expected}
    expected_path = (
        ('attributes', 'password_hint', 0, 'password')
        if isinstance(container, list)
        else ('attributes', 'password_hint', 'password')
    )
    assert notes == [{'path': expected_path, 'matched_substring': 'password'}]


def test_callback_receives_scrubbed_container_before_returning_subset():
    def callback(match: logfire.ScrubMatch):
        if match.path == ('attributes', 'password_hint'):
            assert match.value == {'password': "[Scrubbed due to 'password']", 'keep': 'yes'}
            return {'password': match.value['password']}

    result, notes = Scrubber(None, callback).scrub_value(
        ('attributes',), {'password_hint': {'password': 'hunter2', 'keep': 'yes'}}
    )

    assert result == {'password_hint': {'password': "[Scrubbed due to 'password']"}}
    assert notes == [{'path': ('attributes', 'password_hint', 'password'), 'matched_substring': 'password'}]


def test_matching_key_with_cyclic_value_is_redacted():
    value: dict[str, Any] = {}
    value['password_hint'] = value

    result, notes = Scrubber(None).scrub_value(('attributes',), value)

    assert result == {'password_hint': "[Scrubbed due to 'password']"}
    assert notes == [{'path': ('attributes', 'password_hint'), 'matched_substring': 'password'}]


def test_callback_receives_scrubbed_json_attribute(exporter: TestExporter, config_kwargs: dict[str, Any]):
    def callback(match: logfire.ScrubMatch):
        if match.path == ('attributes', 'password_hint'):
            value = json.loads(match.value)
            assert value == {'password': "[Scrubbed due to 'password']", 'keep': 'yes'}
            return json.dumps({'password': value['password']})

    logfire.configure(**config_kwargs, scrubbing=logfire.ScrubbingOptions(callback=callback))
    logfire.info('Example', password_hint={'password': 'hunter2', 'keep': 'yes'})

    (span,) = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert span['attributes']['password_hint'] == {'password': "[Scrubbed due to 'password']"}


def test_callback_equal_container_copy_only_rewrites_json_when_nested_value_changes():
    def callback(match: logfire.ScrubMatch):
        if match.path == ('attributes', 'data', 'password_hint'):
            return match.value.copy()

    scrubber = Scrubber(None, callback)
    unchanged = '{"password_hint":{"amount":1e400}}'
    assert scrubber.scrub_value(('attributes', 'data'), unchanged) == (unchanged, [])

    changed = '{"password_hint":{"password":"hunter2"}}'
    result, notes = scrubber.scrub_value(('attributes', 'data'), changed)
    assert json.loads(result) == {'password_hint': {'password': "[Scrubbed due to 'password']"}}
    assert notes == [{'path': ('attributes', 'data', 'password_hint', 'password'), 'matched_substring': 'password'}]


def test_callback_changed_container_is_final():
    replacement = {'password': 'allowed'}

    def callback(match: logfire.ScrubMatch):
        if match.path == ('attributes', 'password_hint'):
            return replacement

    result, notes = Scrubber(None, callback).scrub_value(('attributes',), {'password_hint': {'password': 'hunter2'}})

    assert result == {'password_hint': replacement}
    assert notes == [{'path': ('attributes', 'password_hint', 'password'), 'matched_substring': 'password'}]


def test_callback_container_with_ambiguous_equality_is_final():
    class IncomparableDict(dict[str, str]):
        def __eq__(self, other: object) -> bool:
            raise RuntimeError('cannot compare')

    replacement = IncomparableDict(password='allowed')

    def callback(match: logfire.ScrubMatch):
        if match.path == ('attributes', 'password_hint'):
            return replacement

    result, notes = Scrubber(None, callback).scrub_value(
        ('attributes',), {'password_hint': IncomparableDict(password='hunter2')}
    )

    assert result['password_hint'] is replacement
    assert notes == [{'path': ('attributes', 'password_hint', 'password'), 'matched_substring': 'password'}]


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
    # We don't redact (despite containing "password"):
    # - The event name.
    # - The exception stuff.
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
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                    'logfire.scrubbed': IsJson(
                        [
                            {
                                'path': ['otel_events', 0, 'attributes', 'password'],
                                'matched_substring': 'password',
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
                            'exception.message': 'Password: hunter2',
                            'exception.stacktrace': 'wrong and secret',
                            'exception.escaped': 'False',
                        },
                    },
                    {
                        'name': 'exception',
                        'timestamp': 4000000000,
                        'attributes': {
                            'exception.type': 'tests.test_secret_scrubbing.PasswordError',
                            'exception.message': 'Password: hunter2',
                            'exception.stacktrace': 'tests.test_secret_scrubbing.PasswordError: Password: hunter2',
                            'exception.escaped': 'True',
                        },
                    },
                ],
            }
        ]
    )


def test_scrubbing_config(exporter: TestExporter, logs_exporter: TestLogExporter, config_kwargs: dict[str, Any]):
    def callback(match: logfire.ScrubMatch):
        if match.path[-1] == 'my_password':
            return str(match)
        elif match.path[-1] == 'bad_value':
            # OpenTelemetry versions may drop or stringify unsupported objects.
            return match

    config_kwargs['advanced'].log_record_processors = [SimpleLogRecordProcessor(logs_exporter)]
    logfire.configure(
        scrubbing=logfire.ScrubbingOptions(
            extra_patterns=['my_pattern'],
            callback=callback,
        ),
        **config_kwargs,
    )

    # Ignore the version-specific representation of the arbitrary callback object.
    logfire.info('hi', my_password='hunter2', other='matches_my_pattern', bad_value='the_password')

    get_logger(__name__).emit(
        LogRecord(attributes={'my_password': 'hunter2', 'bad_value': 'the_password', 'event.name': 'hi'})
    )

    spans = exporter.exported_spans_as_dict()
    spans[0]['attributes'].pop('bad_value', None)
    assert spans == snapshot(
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

    logs = logs_exporter.exported_logs_as_dicts()
    logs[0]['attributes'].pop('bad_value', None)
    assert logs == snapshot(
        [
            {
                'body': None,
                'severity_number': None,
                'severity_text': None,
                'attributes': {
                    'my_password': (
                        'ScrubMatch('
                        "path=('attributes', 'my_password'), "
                        "value='hunter2', "
                        "pattern_match=<re.Match object; span=(3, 11), match='password'>"
                        ')'
                    ),
                    'event.name': 'hi',
                },
                'timestamp': 2000000000,
                'observed_timestamp': 3000000000,
                'trace_id': 0,
                'span_id': 0,
                'trace_flags': 0,
            }
        ]
    )


def test_dont_scrub_resource(exporter: TestExporter, config_kwargs: dict[str, Any], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(OTEL_RESOURCE_ATTRIBUTES, 'my_password=hunter2,yours=your_password,other=safe=good')
    logfire.configure(**config_kwargs)
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


def test_disable_scrubbing(exporter: TestExporter, logs_exporter: TestLogExporter, config_kwargs: dict[str, Any]):
    config_kwargs['advanced'].log_record_processors = [SimpleLogRecordProcessor(logs_exporter)]
    logfire.configure(**config_kwargs, scrubbing=False)

    config = logfire.DEFAULT_LOGFIRE_INSTANCE.config
    assert config.scrubbing is False
    assert isinstance(config.scrubber, NoopScrubber)

    logfire.info('Password: {user_password}', user_password='my secret password')
    get_logger(__name__).emit(
        LogRecord(attributes={'user_password': 'my secret password', 'event.name': 'Password: {user_password}'})
    )
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
    assert logs_exporter.exported_logs_as_dicts() == snapshot(
        [
            {
                'body': None,
                'severity_number': None,
                'severity_text': None,
                'attributes': {
                    'user_password': 'my secret password',
                    'event.name': 'Password: {user_password}',
                },
                'timestamp': 2000000000,
                'observed_timestamp': 3000000000,
                'trace_id': 0,
                'span_id': 0,
                'trace_flags': 0,
            }
        ]
    )


def test_do_not_scrub(exporter: TestExporter):
    # do_not_scrub is a safe key to provide a crude workaround, but it only works if the matched value is *inside*
    logfire.info(
        'hi',
        x=[
            {'do_not_scrub': 'not_secret'},  # only this works
            {'not_secret': 'do_not_scrub'},
            {'not_secret': {'do_not_scrub': 'foo'}},
        ],
    )
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
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
                    'code.function': 'test_do_not_scrub',
                    'code.lineno': 123,
                    'x': [
                        {'do_not_scrub': 'not_secret'},
                        {'not_secret': "[Scrubbed due to 'secret']"},
                        {'not_secret': "[Scrubbed due to 'secret']"},
                    ],
                    'logfire.json_schema': {'type': 'object', 'properties': {'x': {'type': 'array'}}},
                    'logfire.scrubbed': [
                        {'path': ['attributes', 'x', 1, 'not_secret'], 'matched_substring': 'secret'},
                        {'path': ['attributes', 'x', 2, 'not_secret'], 'matched_substring': 'secret'},
                    ],
                },
            }
        ]
    )


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
                            {'path': ['attributes', 'password'], 'matched_substring': 'secret'},
                            {'path': ['attributes', 'password'], 'matched_substring': 'password'},
                        ]
                    ),
                },
            }
        ]
    )


def test_word_boundaries(exporter: TestExporter):
    logfire.info(
        'hi',
        x=[
            'abcjwt',
            'abc_jwt',
            'abc-jwt',
            'csrf123',
            'csrf_123',
            'csrf/123',
            '456/csrf/123',
        ],
    )
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
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
                    'code.function': 'test_word_boundaries',
                    'code.lineno': 123,
                    'x': [
                        'abcjwt',
                        "[Scrubbed due to '_jwt']",
                        "[Scrubbed due to 'jwt']",
                        'csrf123',
                        "[Scrubbed due to 'csrf_']",
                        "[Scrubbed due to 'csrf']",
                        "[Scrubbed due to 'csrf']",
                    ],
                    'logfire.json_schema': {'type': 'object', 'properties': {'x': {'type': 'array'}}},
                    'logfire.scrubbed': [
                        {'path': ['attributes', 'x', 1], 'matched_substring': '_jwt'},
                        {'path': ['attributes', 'x', 2], 'matched_substring': 'jwt'},
                        {'path': ['attributes', 'x', 4], 'matched_substring': 'csrf_'},
                        {'path': ['attributes', 'x', 5], 'matched_substring': 'csrf'},
                        {'path': ['attributes', 'x', 6], 'matched_substring': 'csrf'},
                    ],
                },
            }
        ]
    )


def test_default_patterns_match_docs():
    """The default scrubbing patterns are documented, so the docs must be kept in sync with the code.

    The docs list is generated from `DEFAULT_PATTERNS`. If it has drifted, this test rewrites
    the docs to match (so a local re-run passes) and then fails, like inline-snapshot's fix mode.
    """
    from logfire._internal.scrubbing import DEFAULT_PATTERNS

    docs = Path(__file__).parent.parent / 'docs' / 'how-to-guides' / 'scrubbing.md'
    content = docs.read_text()

    # `repr` of each pattern reproduces exactly how it's written in the docs code block.
    expected_block = '[\n' + ''.join(f'    {pattern!r},\n' for pattern in DEFAULT_PATTERNS) + ']'

    # Match the ```python [...] ``` block that follows the "default scrubbing patterns" sentence.
    match = re.search(
        r'(Here are the default scrubbing patterns:\n+```python\n)(\[.*?\])(\n```)',
        content,
        re.DOTALL,
    )
    assert match, 'Could not find the default scrubbing patterns code block in the docs'

    if match.group(2) != expected_block:
        docs.write_text(content[: match.start(2)] + expected_block + content[match.end(2) :])
        pytest.fail(
            f'The scrubbing patterns documented in {docs} were out of sync with `DEFAULT_PATTERNS` '
            'in logfire-sdk/logfire/_internal/scrubbing.py. The docs have been updated to match; re-run to confirm.'
        )


def test_logfire_token_prefix_scrubbing(exporter: TestExporter):
    logfire.info(
        'hi',
        x=[
            'pylf_v1_abc123xyz',
            'pylf_v2_sometoken',
            'pylf_v10_longerversion',
            'not_pylf_v1_token',
            'pylf_v1_',
        ],
    )
    # pylf_v\d+_ pattern matches Logfire API token prefixes.
    # Tokens like 'pylf_v1_abc123xyz' get scrubbed, but the prefix alone is kept.
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
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
                    'code.function': 'test_logfire_token_prefix_scrubbing',
                    'code.lineno': 123,
                    'x': [
                        "[Scrubbed due to 'pylf_v1_']",
                        "[Scrubbed due to 'pylf_v2_']",
                        "[Scrubbed due to 'pylf_v10_']",
                        "[Scrubbed due to 'pylf_v1_']",
                        'pylf_v1_',
                    ],
                    'logfire.json_schema': {'type': 'object', 'properties': {'x': {'type': 'array'}}},
                    'logfire.scrubbed': [
                        {'path': ['attributes', 'x', 0], 'matched_substring': 'pylf_v1_'},
                        {'path': ['attributes', 'x', 1], 'matched_substring': 'pylf_v2_'},
                        {'path': ['attributes', 'x', 2], 'matched_substring': 'pylf_v10_'},
                        {'path': ['attributes', 'x', 3], 'matched_substring': 'pylf_v1_'},
                    ],
                },
            }
        ]
    )


def test_oauth_token_names_scrubbed(exporter: TestExporter):
    logfire.info(
        'hi',
        access_token='ya29.a0Af',
        refresh_token='1//0gLk',
        id_token='eyJhbGciOi',
        bearer_token='abc123',
        input_tokens=10,
        max_tokens=100,
        token='kept',
        error='invalid token',
    )
    # A bare `token`, LLM token counts, and prose like 'invalid token' are deliberately not matched.
    attributes = exporter.exported_spans_as_dict()[0]['attributes']
    assert {
        k: attributes[k]
        for k in [
            'access_token',
            'refresh_token',
            'id_token',
            'bearer_token',
            'input_tokens',
            'max_tokens',
            'token',
            'error',
        ]
    } == snapshot(
        {
            'access_token': "[Scrubbed due to 'access_token']",
            'refresh_token': "[Scrubbed due to 'refresh_token']",
            'id_token': "[Scrubbed due to 'id_token']",
            'bearer_token': "[Scrubbed due to 'bearer_token']",
            'input_tokens': 10,
            'max_tokens': 100,
            'token': 'kept',
            'error': 'invalid token',
        }
    )


def test_passphrase_and_signing_keys_scrubbed(exporter: TestExporter):
    logfire.info(
        'hi',
        passphrase='correct horse',
        signing_key='k1',
        hmac_key='k2',
        webhook_hmac_key='k3',
        keyboard_layout='uk',
    )
    attributes = exporter.exported_spans_as_dict()[0]['attributes']
    assert {
        k: attributes[k] for k in ['passphrase', 'signing_key', 'hmac_key', 'webhook_hmac_key', 'keyboard_layout']
    } == snapshot(
        {
            'passphrase': "[Scrubbed due to 'passphrase']",
            'signing_key': "[Scrubbed due to 'signing_key']",
            'hmac_key': "[Scrubbed due to 'hmac_key']",
            'webhook_hmac_key': "[Scrubbed due to 'hmac_key']",
            'keyboard_layout': 'uk',
        }
    )


def test_aws_security_tokens_scrubbed(exporter: TestExporter):
    logfire.info(
        'hi',
        aws_security_token='FwoGZXIvYXdzEA',
        security_token='IQoJb3JpZ2luX2Vj',
        headers={'X-Amz-Security-Token': 'FwoGZXIvYXdzEB'},
        security_level='high',
    )
    attributes = exporter.exported_spans_as_dict(parse_json_attributes=True)[0]['attributes']
    assert {
        k: attributes[k] for k in ['aws_security_token', 'security_token', 'headers', 'security_level']
    } == snapshot(
        {
            'aws_security_token': "[Scrubbed due to 'security_token']",
            'security_token': "[Scrubbed due to 'security_token']",
            'headers': {'X-Amz-Security-Token': "[Scrubbed due to 'Security-Token']"},
            'security_level': 'high',
        }
    )
