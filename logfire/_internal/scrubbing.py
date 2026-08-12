from __future__ import annotations

import copy
import difflib
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict, cast

import typing_extensions
from opentelemetry._logs import LogRecord
from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk.trace import Event
from opentelemetry.trace import Link

from ..exceptions import LogfireConfigError
from .constants import (
    ATTRIBUTES_CONFIG,
    ATTRIBUTES_JSON_SCHEMA_KEY,
    ATTRIBUTES_LOG_LEVEL_NAME_KEY,
    ATTRIBUTES_LOG_LEVEL_NUM_KEY,
    ATTRIBUTES_LOGGING_NAME,
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_PACKAGE_VERSIONS,
    ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY,
    ATTRIBUTES_SAMPLE_RATE_KEY,
    ATTRIBUTES_SCRUBBED_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    ATTRIBUTES_TAGS_KEY,
    MESSAGE_FORMATTED_VALUE_LENGTH_LIMIT,
    RESOURCE_ATTRIBUTES_VERSION,
)
from .integrations.llm_providers import semconv as gen_ai_semconv
from .stack_info import STACK_INFO_KEYS
from .utils import ReadableSpanDict, truncate_string

DEFAULT_PATTERNS: dict[str, str] = {
    'password': 'password',
    'passwd': 'passwd',
    'mysql_pwd': 'mysql_pwd',
    'secret': 'secret',
    'auth': r'auth(?!ors?\b)',
    'credential': 'credential',
    'private_key': 'private[._ -]?key',
    'api_key': 'api[._ -]?key',
    'session': 'session',
    'cookie': 'cookie',
    'social_security': 'social[._ -]?security',
    'credit_card': 'credit[._ -]?card',
    'logfire_token': 'logfire[._ -]?token',
    'pylf_token': r'pylf_v\d+_',
    # The acronyms are required to be surrounded by word boundaries or underscores,
    # to reduce the chance of accidentally matching them in a big blob of random chars, e.g. base64.
    'csrf': r'(?:\b|_)csrf(?:\b|_)',
    'xsrf': r'(?:\b|_)xsrf(?:\b|_)',
    'jwt': r'(?:\b|_)jwt(?:\b|_)',
    'ssn': r'(?:\b|_)ssn(?:\b|_)',
}
"""The scrubbing patterns applied by default, keyed by the name used to refer to them in
[`ScrubbingOptions.disabled_patterns`][logfire.ScrubbingOptions.disabled_patterns]."""

CREDENTIAL_PATTERN_NAMES = frozenset({'logfire_token', 'pylf_token'})
"""Patterns guarding Logfire's own write token, which cannot be disabled."""


JsonPath: typing_extensions.TypeAlias = 'tuple[str | int, ...]'


@dataclass
class ScrubMatch:
    """An object passed to a [`ScrubbingOptions.callback`][logfire.ScrubbingOptions.callback] function."""

    path: JsonPath
    """The path to the value in the span being considered for redaction, e.g. `('attributes', 'password')`."""

    value: Any
    """The value in the span being considered for redaction, e.g. `'my_password'`."""

    pattern_match: re.Match[str]
    """
    The regex match object indicating why the value is being redacted.
    Use `pattern_match.group(0)` to get the matched string.
    """


ScrubCallback = Callable[[ScrubMatch], Any]


def _search(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    """Find the first match with any width.

    A zero-width match would redact a value while reporting nothing as the reason, and a pattern
    that can only match zero-width can never point at anything sensitive, so those are not matches.
    """
    return next((match for match in pattern.finditer(text) if match.end() > match.start()), None)


class ScrubbedNote(TypedDict):
    path: JsonPath
    matched_substring: str


@dataclass
class ScrubbingOptions:
    """Options for redacting sensitive data."""

    callback: ScrubCallback | None = None
    """
    A function that is called for each match found by the scrubber.
    If it returns `None`, the value is redacted.
    Otherwise, the returned value replaces the matched value.
    The function accepts a single argument of type [`logfire.ScrubMatch`][logfire.ScrubMatch].
    """

    extra_patterns: Sequence[str] | None = None
    """
    A sequence of regular expressions to detect sensitive data that should be redacted.
    For example, the default includes `'password'`, `'secret'`, and `'api[._ -]?key'`.
    The specified patterns are combined with the default patterns.

    These are matched while the span is being created, on the thread creating it, so an
    expensive pattern slows down the instrumented application itself. Avoid nested quantifiers
    such as `(a+)+`, which can take exponential time on values you don't control.
    """

    disabled_patterns: Sequence[str] | None = None
    """
    Names of default patterns to turn off, e.g. `['session']` to stop redacting values because
    they look session-related. Passing a name that isn't a default pattern raises an error listing
    the valid names, which are also documented in the scrubbing guide.

    Disabling a pattern turns it off everywhere. To keep a pattern on and make an exception for
    particular values, use `callback` instead.
    """

    safe_keys: Sequence[str] | None = None
    """
    Attribute names that are never redacted, in addition to the ones Logfire already treats as safe.

    A safe key is matched exactly, at every nesting depth, and exempts **the entire value beneath
    it** — nothing inside a safe key is scrubbed, however deeply nested, except for the patterns
    guarding Logfire's own write token. Use it for keys you know are always safe to send.
    """

    def __post_init__(self) -> None:
        extra_patterns = self.extra_patterns = _check_string_sequence(self.extra_patterns, 'extra_patterns')
        disabled_patterns = self.disabled_patterns = _check_string_sequence(self.disabled_patterns, 'disabled_patterns')
        safe_keys = self.safe_keys = _check_string_sequence(self.safe_keys, 'safe_keys')

        for i, pattern in enumerate(extra_patterns):
            try:
                # Compiled individually rather than only as part of the joined pattern, so that the
                # error names the offending pattern and reports a position relative to it.
                compiled = re.compile(pattern)
            except re.error as e:
                raise LogfireConfigError(f'Invalid regex in `extra_patterns` at index {i}: {pattern!r} - {e}') from e
            # A pattern that can match nothing matches at position 0 of every value, so it would
            # redact all of them. Probing a sample string catches the zero-width patterns that
            # don't match the empty string itself, such as `\b`.
            probe = 'logfire scrubbing probe 0123456789 _-.'
            if compiled.match('') is not None or any(m.start() == m.end() for m in compiled.finditer(probe)):
                raise LogfireConfigError(
                    f'`extra_patterns` contains a pattern matching the empty string at index {i}: {pattern!r}. '
                    'It would match every value and redact all of them.'
                )

        for name in disabled_patterns:
            if name not in DEFAULT_PATTERNS:
                suggestions = difflib.get_close_matches(name, DEFAULT_PATTERNS)
                did_you_mean = f' Did you mean {suggestions[0]!r}?' if suggestions else ''
                raise LogfireConfigError(
                    f'Unknown scrubbing pattern name {name!r} in `disabled_patterns`.{did_you_mean} '
                    '`disabled_patterns` takes the names of default patterns, not regexes - '
                    'use `extra_patterns` to add a regex. '
                    f'Known names: {", ".join(sorted(DEFAULT_PATTERNS))}.'
                )
            if name in CREDENTIAL_PATTERN_NAMES:
                raise LogfireConfigError(
                    f"Refusing to disable the scrubbing pattern {name!r}: it guards Logfire's own write token, "
                    'which would otherwise be recorded in spans and sent to Logfire, where anyone with read '
                    'access to the project can see it. To make an exception for a specific value, keep the '
                    'pattern enabled and return that value unredacted from `ScrubbingOptions.callback` instead.'
                )

        for i, key in enumerate(safe_keys):
            if not key.strip():
                raise LogfireConfigError(
                    f'`safe_keys` contains an empty entry at index {i}. '
                    'Safe keys are matched against attribute names exactly, so an empty key can never match.'
                )
            for name in sorted(CREDENTIAL_PATTERN_NAMES):
                if re.search(DEFAULT_PATTERNS[name], key, re.IGNORECASE):
                    raise LogfireConfigError(
                        f'Refusing to add {key!r} to `safe_keys`: it matches the {name!r} pattern, which guards '
                        "Logfire's own write token. Use `ScrubbingOptions.callback` to make an exception for a "
                        'specific value instead.'
                    )


def _check_string_sequence(value: object, field_name: str) -> tuple[str, ...]:
    """Reject anything that isn't really a sequence of strings.

    A bare string is a `Sequence[str]` that iterates one character at a time, and a mapping
    iterates its keys, so both would otherwise be accepted and mean something unintended.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        raise LogfireConfigError(
            f'`{field_name}` must be a sequence of strings, got the string {value!r}. '
            f'A bare string is iterated one character at a time. Pass [{value!r}].'
        )
    if not isinstance(value, Sequence):
        raise LogfireConfigError(f'`{field_name}` must be a sequence of strings, got {type(value).__name__}.')
    items: list[str] = []
    for i, item in enumerate(cast('Sequence[Any]', value)):
        if not isinstance(item, str):
            raise LogfireConfigError(
                f'`{field_name}` must contain only strings, but the entry at index {i} is {item!r}.'
            )
        items.append(item)
    return tuple(items)


class BaseScrubber(ABC):
    # These keys and everything within are safe to keep in spans, even if they match the scrubbing pattern.
    # Some of these are just here for performance.
    SAFE_KEYS = {
        ATTRIBUTES_MESSAGE_KEY,  # Formatted field values are scrubbed separately
        ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
        ATTRIBUTES_JSON_SCHEMA_KEY,
        ATTRIBUTES_TAGS_KEY,
        ATTRIBUTES_LOG_LEVEL_NAME_KEY,
        ATTRIBUTES_LOG_LEVEL_NUM_KEY,
        ATTRIBUTES_SPAN_TYPE_KEY,
        ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY,
        ATTRIBUTES_SAMPLE_RATE_KEY,
        ATTRIBUTES_LOGGING_NAME,
        ATTRIBUTES_SCRUBBED_KEY,
        ATTRIBUTES_CONFIG,
        ATTRIBUTES_PACKAGE_VERSIONS,
        RESOURCE_ATTRIBUTES_VERSION,
        *STACK_INFO_KEYS,
        'exception.stacktrace',
        'exception.type',
        'exception.message',
        'error.type',
        'http.method',
        'http.status_code',
        'http.scheme',
        'http.url',
        'http.target',
        'http.route',
        'db.statement',
        'db.query.text',
        'db.plan',
        'fastapi.route.name',
        'fastapi.route.operation_id',
        'url.full',
        'url.path',
        'url.query',
        'event.name',
        'agent_session_id',
        'do_not_scrub',
        'binary_content',
        'pydantic_ai.all_messages',
        'rpc.method',
        'model_request_parameters',
        'langsmith.metadata.session_id',
        'langsmith.trace.session_name',
        gen_ai_semconv.INPUT_MESSAGES,
        gen_ai_semconv.OUTPUT_MESSAGES,
        gen_ai_semconv.SYSTEM_INSTRUCTIONS,
        gen_ai_semconv.TOOL_DEFINITIONS,
        gen_ai_semconv.TOOL_NAME,
        gen_ai_semconv.TOOL_CALL_ID,
        gen_ai_semconv.INPUT_TOKENS,
        gen_ai_semconv.OUTPUT_TOKENS,
        gen_ai_semconv.CACHE_READ_INPUT_TOKENS,
        gen_ai_semconv.CACHE_CREATION_INPUT_TOKENS,
        gen_ai_semconv.USAGE_RAW,
        gen_ai_semconv.CONVERSATION_ID,
        gen_ai_semconv.SYSTEM,
        gen_ai_semconv.PROVIDER_NAME,
        gen_ai_semconv.REQUEST_MODEL,
        gen_ai_semconv.RESPONSE_MODEL,
    }

    safe_keys: Collection[str] = SAFE_KEYS
    """`SAFE_KEYS` plus any keys the user added via `ScrubbingOptions.safe_keys`."""

    user_safe_keys: Collection[str] = frozenset()
    """Only the keys the user added, which stay subject to the credential patterns."""

    @abstractmethod
    def scrub_span(self, span: ReadableSpanDict): ...

    @abstractmethod
    def scrub_log(self, log: LogRecord) -> LogRecord: ...

    @abstractmethod
    def scrub_value(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]: ...

    @abstractmethod
    def scrub_credentials(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]: ...


class NoopScrubber(BaseScrubber):
    def scrub_span(self, span: ReadableSpanDict):
        pass

    def scrub_log(self, log: LogRecord) -> LogRecord:
        return log

    def scrub_value(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]:  # pragma: no cover
        return value, []

    def scrub_credentials(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]:  # pragma: no cover
        return value, []


NOOP_SCRUBBER = NoopScrubber()


class Scrubber(BaseScrubber):
    """Redacts potentially sensitive data."""

    def __init__(
        self,
        patterns: Sequence[str] | None,
        callback: ScrubCallback | None = None,
        disabled_patterns: Sequence[str] | None = None,
        safe_keys: Sequence[str] | None = None,
    ):
        # See ScrubbingOptions for more info on these parameters.
        disabled = set(disabled_patterns or ())
        all_patterns = [name for key, name in DEFAULT_PATTERNS.items() if key not in disabled]
        all_patterns += patterns or []
        # Each pattern is wrapped so that a top-level `|` in one of them can't change how the
        # others are grouped. The group is non-capturing so that backreferences in user patterns
        # keep referring to the user's own groups.
        self._pattern = re.compile('|'.join(f'(?:{p})' for p in all_patterns), re.IGNORECASE | re.DOTALL)
        self._callback = callback
        # Applied beneath safe keys, which is why these patterns can't be disabled.
        self.credential_pattern = re.compile(
            '|'.join(f'(?:{DEFAULT_PATTERNS[name]})' for name in sorted(CREDENTIAL_PATTERN_NAMES)),
            re.IGNORECASE | re.DOTALL,
        )
        self.user_safe_keys = set(safe_keys or ())
        self.safe_keys = BaseScrubber.SAFE_KEYS | self.user_safe_keys

    def scrub_log(self, log: LogRecord) -> LogRecord:
        span_scrubber = SpanScrubber(self)
        return span_scrubber.scrub_log(log)

    def scrub_span(self, span: ReadableSpanDict):
        scope = span['instrumentation_scope']
        if scope and scope.name in ['logfire.openai', 'logfire.anthropic']:
            return

        span_scrubber = SpanScrubber(self)
        span_scrubber.scrub_span(span)
        if span_scrubber.scrubbed:
            attributes = span['attributes']
            already_scrubbed = cast('str', attributes.get(ATTRIBUTES_SCRUBBED_KEY, '[]'))
            try:
                already_scrubbed = cast('list[ScrubbedNote]', json.loads(already_scrubbed))
            except json.JSONDecodeError:  # pragma: no cover
                already_scrubbed = []
            span['attributes'] = {
                **attributes,
                ATTRIBUTES_SCRUBBED_KEY: json.dumps(already_scrubbed + span_scrubber.scrubbed),
            }

    def scrub_value(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]:
        span_scrubber = SpanScrubber(self)
        result = span_scrubber.scrub(path, value)
        return result, span_scrubber.scrubbed

    def scrub_credentials(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]:
        """Apply only the patterns guarding Logfire's own token, for values exempt from the rest."""
        span_scrubber = SpanScrubber(self)
        result = span_scrubber.scrub(path, value, self.credential_pattern)
        return result, span_scrubber.scrubbed


class SpanScrubber:
    """Does the actual scrubbing work.

    This class is separate from Scrubber so that it can be instantiated more regularly
    and hold and mutate state about the span being scrubbed, specifically the scrubbed notes.
    """

    def __init__(self, parent: Scrubber):
        self._pattern = parent._pattern  # pyright: ignore[reportPrivateUsage]
        self._callback = parent._callback  # pyright: ignore[reportPrivateUsage]
        self._credential_pattern = parent.credential_pattern
        self._safe_keys = parent.safe_keys
        self._user_safe_keys = parent.user_safe_keys
        self.scrubbed: list[ScrubbedNote] = []
        self.did_scrub = False

    def scrub_span(self, span: ReadableSpanDict):
        # We need to use BoundedAttributes because:
        # 1. For events and links, we get an error otherwise:
        #      https://github.com/open-telemetry/opentelemetry-python/issues/3761
        # 2. The callback might return a value that isn't of the type required by OTEL,
        #      in which case BoundAttributes will discard it to prevent an error.
        # TODO silently throwing away the result is bad, and BoundedAttributes is bad for performance.
        new_attributes = self.scrub(('attributes',), span['attributes'])
        if self.did_scrub:
            span['attributes'] = BoundedAttributes(attributes=new_attributes)

        span['events'] = [
            Event(
                # We don't scrub the event name because in theory it should be a low-cardinality general description,
                # not containing actual data. The same applies to the span name, which just isn't mentioned here.
                name=event.name,
                attributes=BoundedAttributes(attributes=self.scrub_event_attributes(event, i)),
                timestamp=event.timestamp,
            )
            for i, event in enumerate(span['events'])
        ]
        span['links'] = [
            Link(
                context=link.context,
                attributes=BoundedAttributes(attributes=self.scrub(('links', i, 'attributes'), link.attributes)),
            )
            for i, link in enumerate(span['links'])
        ]

    def scrub_log(self, log: LogRecord) -> LogRecord:
        new_attributes: dict[str, Any] | None = self.scrub(('attributes',), log.attributes)
        new_body = self.scrub(('log_body',), log.body)

        if not self.did_scrub:
            return log

        if self.scrubbed:
            new_attributes = new_attributes or {}
            new_attributes[ATTRIBUTES_SCRUBBED_KEY] = json.dumps(self.scrubbed)

        result = copy.copy(log)
        result.attributes = BoundedAttributes(attributes=new_attributes)
        result.body = new_body
        return result

    def scrub_event_attributes(self, event: Event, index: int):
        attributes = event.attributes or {}
        path = ('otel_events', index, 'attributes')
        new_attributes = self.scrub(path, attributes)
        # We used to scrub exception messages here, git blame this line if you want to restore that logic.
        return new_attributes

    def scrub(self, path: JsonPath, value: Any, pattern: re.Pattern[str] | None = None) -> Any:
        """Redacts sensitive data from `value`, recursing into nested sequences and mappings.

        `path` is a list of keys and indices leading to `value` in the span.
        Similar to the truncation code, it should use the field names in the frontend, e.g. `otel_events`.

        `pattern` defaults to the full set. It narrows to the credential patterns beneath a safe key,
        which exempts its contents from everything else but never from those.
        """
        pattern = self._pattern if pattern is None else pattern
        if isinstance(value, str):
            if match := _search(pattern, value):
                if match.span() == (0, len(value)):
                    # If the *whole* string matches, e.g. the value is literally 'password' and nothing more,
                    # it's considered safe.
                    return value
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    return self._redact(ScrubMatch(path, value, match))
                else:
                    return json.dumps(self.scrub(path, value, pattern))
        elif isinstance(value, Sequence):
            return [self.scrub(path + (i,), x, pattern) for i, x in enumerate(cast('Sequence[Any]', value))]
        elif isinstance(value, Mapping):
            result: dict[str, Any] = {}
            for k, v in cast('Mapping[str, Any]', value).items():
                if k in self._user_safe_keys:
                    # A user safe key names arbitrary application data, so it is exempt from
                    # everything except the patterns guarding Logfire's own token.
                    result[k] = self.scrub(path + (k,), v, self._credential_pattern)
                elif k in self._safe_keys and pattern is not self._credential_pattern:
                    result[k] = v
                elif match := _search(pattern, k):
                    redacted = self._redact(ScrubMatch(path + (k,), v, match))
                    if isinstance(redacted, str) and isinstance(v, Sequence) and not isinstance(v, str):
                        redacted = [redacted]
                    result[k] = redacted
                else:
                    result[k] = self.scrub(path + (k,), v, pattern)
            return result
        return value

    def _redact(self, match: ScrubMatch) -> Any:
        if self._callback and (result := self._callback(match)) is not None:
            self.did_scrub = self.did_scrub or result is not match.value
            return result
        self.did_scrub = True
        matched_substring = match.pattern_match.group(0)
        self.scrubbed.append(ScrubbedNote(path=match.path, matched_substring=matched_substring))
        return f'[Scrubbed due to {matched_substring!r}]'


class MessageValueCleaner:
    """Scrubs and truncates formatted field values to be included in the message attribute.

    Use to construct the message for a single span, e.g:

        cleaner = MessageValueCleaner(scrubber, check_keys=...)
        message_parts = [cleaner.clean_value(field_name, str(value)) for field_name, value in fields]
        message = <construct from message parts>
        attributes = {**other_attributes, **cleaner.extra_attrs(), ATTRIBUTES_MESSAGE_KEY: message}

    check_keys determines whether the key should be accounted for in scrubbing.
    Set to False if the user explicitly provided the key, e.g. `logfire.info(f'... {password} ...')`
    means that the password is clearly expected to be logged.
    The password will therefore not be scrubbed here and will appear in the message.
    However it may still be scrubbed out of the attributes, just because that process is independent.
    """

    def __init__(self, scrubber: BaseScrubber, *, check_keys: bool):
        self.scrubber = scrubber
        self.scrubbed: list[ScrubbedNote] = []
        self.check_keys = check_keys

    def clean_value(self, field_name: str, value: str) -> str:
        # Scrub before truncating so that the scrubber can see the full value.
        # For example, if the value contains 'password=123' and 'password' is replaced by '...'
        # because of truncation, then that leaves '=123' in the message, which is not good.
        if field_name in self.scrubber.user_safe_keys:
            # Same exception as the attribute path: exempt from everything but the credential patterns.
            value, scrubbed_notes = self.scrubber.scrub_credentials(('message', field_name), value)
            self.scrubbed.extend(scrubbed_notes)
        elif field_name not in self.scrubber.safe_keys:
            if self.check_keys:
                # Scrubbing a dict with only one key is a simple way to check that key during the scrubbing.
                scrubbed_value, scrubbed_notes = self.scrubber.scrub_value(('message',), {field_name: value})
                value = scrubbed_value[field_name]
            else:
                # Whereas having the key in the path doesn't affect the scrubbing result,
                # so this only looks at `value` itself.
                value, scrubbed_notes = self.scrubber.scrub_value(('message', field_name), value)
            self.scrubbed.extend(scrubbed_notes)
        return self.truncate(value)

    def truncate(self, value: str) -> str:
        return truncate_string(value, max_length=MESSAGE_FORMATTED_VALUE_LENGTH_LIMIT)

    def extra_attrs(self) -> dict[str, Any]:
        if self.scrubbed:
            return {ATTRIBUTES_SCRUBBED_KEY: json.dumps(self.scrubbed)}
        return {}
