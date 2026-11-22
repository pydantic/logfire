from __future__ import annotations

import copy
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict, cast

import typing_extensions
from opentelemetry._logs import LogRecord
from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk.trace import Event
from opentelemetry.trace import Link, Status

from logfire.types import StringValue

from .constants import (
    ATTRIBUTES_CONFIG,
    ATTRIBUTES_JSON_SCHEMA_KEY,
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
from .json_encoder import logfire_json_dumps
from .stack_info import STACK_INFO_KEYS
from .utils import ReadableSpanDict, handle_internal_errors, truncate_string

DEFAULT_PATTERNS = [
    'password',
    'passwd',
    'mysql_pwd',
    'secret',
    r'auth(?!ors?\b)',
    'credential',
    'private[._ -]?key',
    'passphrase',
    '(?:signing|hmac)[._ -]?key',
    'api[._ -]?key',
    'session',
    'cookie',
    'social[._ -]?security',
    'credit[._ -]?card',
    'logfire[._ -]?token',
    # OAuth-style token names. A bare 'token' is left out because it would also match LLM usage fields like input_tokens.
    r'(?:access|refresh|bearer|(?:\b|_)id)[._ -]?token',
    'security[._ -]?token',
    r'pylf_v\d+_',
    *[
        # Require these to be surrounded by word boundaries or underscores,
        # to reduce the chance of accidentally matching them in a big blob of random chars, e.g. base64.
        rf'(?:\b|_){acronym}(?:\b|_)'
        for acronym in [
            'csrf',
            'xsrf',
            'jwt',
            'ssn',
        ]
    ],
]

# Every default pattern starts matching at one of these characters. Checking this
# inexpensive character class first avoids trying every alternative at every
# position in large strings. Custom patterns are not constrained by this prefix.
_DEFAULT_PATTERN_START_CHARS = 'pmsacljx_rbih'
_DEFAULT_PATTERN = rf'(?=[{_DEFAULT_PATTERN_START_CHARS}])(?:{"|".join(DEFAULT_PATTERNS)})'
_MAX_UNCHANGED_MATCHES = 100

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


class ScrubbedNote(TypedDict):
    path: JsonPath
    matched_substring: str


def _is_unchanged_value(value: Any, result: Any) -> bool:
    if result is value:
        return True
    if type(result) is not type(value):
        return False
    try:
        return bool(result == value)
    except Exception:
        # Some values do not provide a single Boolean result for equality.
        return False


@dataclass
class ScrubbingOptions:
    """Options for redacting sensitive data."""

    callback: ScrubCallback | None = None
    """
    A function that is called for each match found by the scrubber.
    If it returns `None`, the value is redacted.
    Otherwise, the returned value replaces the matched value.
    Logfire scrubs each value before checking whether its key matches. A callback for a matching key
    receives that scrubbed value. A different value returned by the callback is treated as final.
    If a value is returned unchanged or as an equal copy of the same type, Logfire checks other patterns at the
    same position, then later matches in the string. This applies to both matching keys and string values.
    After 100 allowed matches in one string, Logfire redacts the value to bound the search cost.
    Do not mutate the original value in place: Logfire may not detect the change.
    The function accepts a single argument of type [`logfire.ScrubMatch`][logfire.ScrubMatch].
    It may run on a background thread when scrubbing spans. Message formatting calls it on the calling thread.
    """

    extra_patterns: Sequence[str] | None = None
    """
    A sequence of regular expressions to detect sensitive data that should be redacted.
    For example, the default includes `'password'`, `'secret'`, and `'api[._ -]?key'`.
    The specified patterns are combined with the default patterns.
    """

    transform_string: Callable[[StringValue], str] | None = None
    """Transform string values before pattern matching, including values under safe keys.

    Span names, status descriptions, span event names, and OpenTelemetry log-record event names are also transformed,
    without pattern matching.
    Root Logfire control and source attributes, such as `logfire.span_type` and `code.filepath`, are excluded.
    Nested fields with the same names are transformed.

    The callback receives a [`logfire.types.StringValue`][logfire.types.StringValue] with the path and string value.
    It may run on a background thread when scrubbing spans. Message formatting calls it on the calling thread.
    String span messages, tag values, and the exception details printed by the console also call it
    on the calling thread when a span record is emitted, even if console output is disabled.
    This includes pending records emitted when a span starts, before any background span scrubbing.
    A later scrub pass may transform those values again.
    If the message is absent or empty, Logfire uses the span name as the input for the new message.
    An empty result stays empty in the span, and the console displays `<empty message>`.
    A nonempty, non-string `logfire.msg` attribute is left unchanged, including any strings nested inside it.
    If the callback raises, Logfire logs the error and keeps the input string.
    """


class BaseScrubber(ABC):
    # Root SDK control and source attributes: skip pattern matching and transform_string.
    # This is a subset of SAFE_KEYS.
    NO_TRANSFORM_KEYS = {
        ATTRIBUTES_LOG_LEVEL_NUM_KEY,
        ATTRIBUTES_SPAN_TYPE_KEY,
        ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY,
        ATTRIBUTES_SAMPLE_RATE_KEY,
        *STACK_INFO_KEYS,
        # Formatted field values are scrubbed separately,
        # and then the span or log processor transforms the whole message
        ATTRIBUTES_MESSAGE_KEY,
    }

    # Structured content with prose: transform strings and match nested keys,
    # but do not pattern-match string values. This is a subset of SAFE_KEYS.
    KEY_ONLY_KEYS = {
        'pydantic_ai.all_messages',
        gen_ai_semconv.INPUT_MESSAGES,
        gen_ai_semconv.OUTPUT_MESSAGES,
        gen_ai_semconv.SYSTEM_INSTRUCTIONS,
    }

    # All keys whose own names are exempt from pattern matching. By default,
    # their entire subtree also skips patterns but still transforms strings.
    # NO_TRANSFORM_KEYS also skip transformation at the attribute root; KEY_ONLY_KEYS instead match
    # nested keys while leaving string values exempt from pattern matching.
    SAFE_KEYS = {
        *NO_TRANSFORM_KEYS,
        *KEY_ONLY_KEYS,
        ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
        ATTRIBUTES_JSON_SCHEMA_KEY,
        ATTRIBUTES_TAGS_KEY,
        ATTRIBUTES_LOGGING_NAME,
        ATTRIBUTES_SCRUBBED_KEY,
        ATTRIBUTES_CONFIG,
        ATTRIBUTES_PACKAGE_VERSIONS,
        RESOURCE_ATTRIBUTES_VERSION,
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
        'rpc.method',
        'model_request_parameters',
        'langsmith.metadata.session_id',
        'langsmith.trace.session_name',
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

    @abstractmethod
    def scrub_span(self, span: ReadableSpanDict): ...

    @abstractmethod
    def scrub_log(self, log: LogRecord) -> LogRecord: ...

    @abstractmethod
    def scrub_value(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]: ...

    @abstractmethod
    def transform_message(self, value: str) -> str: ...

    @abstractmethod
    def transform_console_fields(self, span: ReadableSpanDict) -> None: ...

    @abstractmethod
    def transform_log_event_name(self, value: str) -> str: ...


class NoopScrubber(BaseScrubber):
    def scrub_span(self, span: ReadableSpanDict):  # pragma: no cover
        # The span processor graph omits scrubbing when it is disabled.
        pass

    def scrub_log(self, log: LogRecord) -> LogRecord:
        return log

    def scrub_value(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]:  # pragma: no cover
        return value, []

    def transform_message(self, value: str) -> str:
        return value

    def transform_console_fields(self, span: ReadableSpanDict) -> None:
        pass

    def transform_log_event_name(self, value: str) -> str:
        return value


NOOP_SCRUBBER = NoopScrubber()


class Scrubber(BaseScrubber):
    """Redacts potentially sensitive data."""

    def __init__(
        self,
        patterns: Sequence[str] | None,
        callback: ScrubCallback | None = None,
        transform_string: Callable[[StringValue], str] | None = None,
    ):
        # See ScrubbingOptions for more info on these parameters.
        patterns = [_DEFAULT_PATTERN, *(patterns or [])]
        self._pattern = re.compile('|'.join(patterns), re.IGNORECASE | re.DOTALL)
        self._individual_patterns = tuple(
            re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in [*DEFAULT_PATTERNS, *patterns[1:]]
        )
        self._callback = callback
        self._transform_string = transform_string

    def scrub_log(self, log: LogRecord) -> LogRecord:
        span_scrubber = SpanScrubber(self)
        return span_scrubber.scrub_log(log)

    def scrub_span(self, span: ReadableSpanDict):
        scope = span['instrumentation_scope']
        span_scrubber = SpanScrubber(self, scope_name=scope.name if scope else None)
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

    def transform_message(self, value: str) -> str:
        if self._transform_string is None:
            return value
        return SpanScrubber(self)._safely_transform_string(  # pyright: ignore[reportPrivateUsage]
            ('attributes', ATTRIBUTES_MESSAGE_KEY), value
        )

    def transform_console_fields(self, span: ReadableSpanDict) -> None:
        """Transform the fields printed by the console before background scrubbing."""
        if self._transform_string is None:
            return

        with handle_internal_errors:
            attributes = span['attributes']
            message = attributes.get(ATTRIBUTES_MESSAGE_KEY) or span['name']
            if isinstance(message, str) and (transformed := self.transform_message(message)) != message:
                span['attributes'] = {**attributes, ATTRIBUTES_MESSAGE_KEY: transformed}

        SpanScrubber(self).transform_console_fields(span)

    def transform_log_event_name(self, value: str) -> str:
        if self._transform_string is None:
            return value
        return SpanScrubber(self)._safely_transform_string(('otel_log_event_name',), value)  # pyright: ignore[reportPrivateUsage]


class SpanScrubber:
    """Does the actual scrubbing work.

    This class is separate from Scrubber so that it can be instantiated more regularly
    and hold and mutate state about the span being scrubbed, specifically the scrubbed notes.
    """

    def __init__(self, parent: Scrubber, *, scope_name: str | None = None):
        self._pattern = parent._pattern  # pyright: ignore[reportPrivateUsage]
        self._individual_patterns = parent._individual_patterns  # pyright: ignore[reportPrivateUsage]
        self._callback = parent._callback  # pyright: ignore[reportPrivateUsage]
        self._transform_string = parent._transform_string  # pyright: ignore[reportPrivateUsage]
        self.scrubbed: list[ScrubbedNote] = []
        self.scrub_count = 0
        self._is_legacy_llm_scope = scope_name in ('logfire.openai', 'logfire.anthropic')
        self._is_legacy_openai_scope = scope_name == 'logfire.openai'

    def _safely_transform_string(self, path: JsonPath, value: str) -> str:
        if self._transform_string is None:
            return value
        transformed = value
        with handle_internal_errors:
            transformed = self._transform_string(StringValue(path, value))
        return transformed

    def transform_console_fields(self, span: ReadableSpanDict) -> None:
        attributes = span['attributes']
        tags = attributes.get(ATTRIBUTES_TAGS_KEY)
        if isinstance(tags, (list, tuple)):
            transformed_tags = tuple(self.scrub(('attributes', ATTRIBUTES_TAGS_KEY), tags, in_safe_key=True))
            if transformed_tags != tags:
                span['attributes'] = {**attributes, ATTRIBUTES_TAGS_KEY: transformed_tags}

        for i, event in enumerate(span['events']):
            if event.name != 'exception':
                continue
            if not event.attributes:
                break
            event_attributes = event.attributes
            transformed_attributes = dict(event_attributes)
            for key in ('exception.type', 'exception.message', 'exception.stacktrace'):
                value = event_attributes.get(key)
                if isinstance(value, str):
                    transformed_attributes[key] = self.scrub(
                        ('otel_events', i, 'attributes', key), value, in_safe_key=True
                    )
            if transformed_attributes != event_attributes:
                events = list(span['events'])
                events[i] = Event(name=event.name, attributes=transformed_attributes, timestamp=event.timestamp)
                span['events'] = events
            break

    def scrub_span(self, span: ReadableSpanDict):
        span['name'] = self._safely_transform_string(('span_name',), span['name'])
        status = span['status']
        if status.description is not None and self._transform_string is not None:
            span['status'] = Status(
                status_code=status.status_code,
                description=self._safely_transform_string(('otel_status_message',), status.description),
            )

        # We need to use BoundedAttributes because:
        # 1. For events and links, we get an error otherwise:
        #      https://github.com/open-telemetry/opentelemetry-python/issues/3761
        # 2. The callback might return a value that isn't of the type required by OTEL;
        #      BoundedAttributes handles it according to the installed OTEL version.
        # TODO silently throwing away the result is bad, and BoundedAttributes is bad for performance.
        new_attributes = self.scrub(('attributes',), span['attributes'])
        if self.scrub_count:
            span['attributes'] = BoundedAttributes(attributes=new_attributes)

        span['events'] = [
            Event(
                name=self._safely_transform_string(('otel_events', i, 'name'), event.name),
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

        if not self.scrub_count:
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

    def scrub(self, path: JsonPath, value: Any, in_safe_key: bool = False, key_only: bool = False) -> Any:
        """Redacts sensitive data from `value`, recursing into nested sequences and mappings.

        `path` is a list of keys and indices leading to `value` in the span.
        Similar to the truncation code, it should use the field names in the frontend, e.g. `otel_events`.
        """
        if type(value) in (int, float, bool, type(None)):
            return value
        if isinstance(value, str):
            if value.lstrip().startswith(('{', '[')):
                try:
                    decoded = json.loads(value)
                    scrub_count_before = self.scrub_count
                    scrubbed = self.scrub(path, decoded, in_safe_key, key_only)
                    return logfire_json_dumps(scrubbed) if self.scrub_count != scrub_count_before else value
                except (ValueError, RecursionError):
                    pass
            transformed = self._safely_transform_string(path, value)
            if transformed != value:
                self.scrub_count += 1
                value = transformed
            if isinstance(value, str) and not in_safe_key and not key_only and (match := self._pattern.search(value)):
                if match.span() == (0, len(value)):
                    # If the *whole* string matches, e.g. the value is literally 'password' and nothing more,
                    # it's considered safe.
                    return value
                return self._scrub_matches(path, value, match)
        elif isinstance(value, (bytes, bytearray, memoryview)):
            # Iterating over a binary value yields integers, so recursing into it would rewrite
            # the value into a sequence of ints. Decode it instead, so text hidden in bytes is
            # still scrubbed.
            binary = bytes(cast(Any, value))
            try:
                text = binary.decode()
            except UnicodeDecodeError:
                return binary
            scrubbed = self.scrub(path, text, in_safe_key, key_only)
            return binary if scrubbed == text else scrubbed
        elif isinstance(value, Sequence):
            return [
                self.scrub(path + (i,), x, in_safe_key, key_only) for i, x in enumerate(cast('Sequence[Any]', value))
            ]
        elif isinstance(value, Mapping):
            result: dict[Any, Any] = {}
            legacy_attributes = self._is_legacy_llm_scope and path == ('attributes',)
            legacy_request = self._is_legacy_llm_scope and path == ('attributes', 'request_data')
            for k, v in cast('Mapping[Any, Any]', value).items():
                # Legacy provider payloads can contain user text. Match nested keys such as
                # tool-call "password", but do not treat words in message text as secrets.
                scoped_content = legacy_attributes and (
                    k in ('request_data', 'response_data') or (k == 'events' and self._is_legacy_openai_scope)
                )
                # Tool and response schemas describe argument names. Preserve those keys,
                # while still allowing transform_string to change their string values.
                legacy_definition = legacy_request and k in ('tools', 'functions', 'response_format')
                if path == ('attributes',) and k in BaseScrubber.NO_TRANSFORM_KEYS:
                    result[k] = v
                elif legacy_definition or (k in BaseScrubber.SAFE_KEYS and k not in BaseScrubber.KEY_ONLY_KEYS):
                    result[k] = (
                        self.scrub(path + (k,), v, in_safe_key=True) if self._transform_string is not None else v
                    )
                else:
                    child_path = path + (k,)
                    scrubbed = self.scrub(
                        child_path, v, in_safe_key, key_only or scoped_content or k in BaseScrubber.KEY_ONLY_KEYS
                    )
                    if not in_safe_key and isinstance(k, str) and (match := self._pattern.search(k)):
                        redacted = self._scrub_matches(child_path, scrubbed, match)
                        if (
                            isinstance(redacted, str)
                            and isinstance(v, Sequence)
                            and not isinstance(v, (str, bytes, bytearray, memoryview))
                        ):
                            redacted = [redacted]
                        result[k] = redacted
                    else:
                        result[k] = scrubbed
            return result
        return value

    def _scrub_matches(self, path: JsonPath, value: Any, match: re.Match[str]) -> Any:
        text = match.string
        unchanged_matches = 0
        while True:
            result = self._redact(ScrubMatch(path, value, match))
            if not _is_unchanged_value(value, result):
                return result
            unchanged_matches += 1
            if unchanged_matches >= _MAX_UNCHANGED_MATCHES:
                self.scrub_count += 1
                return '[Scrubbed due to too many allowed matches]'
            # The combined regex reports only its first alternative at a position.
            # Inspect the other rules only after that match was allowed.
            first_candidate = True
            for pattern in self._individual_patterns:
                candidate = pattern.match(text, match.start())
                if candidate is None:
                    continue
                if first_candidate:
                    first_candidate = False
                    continue
                result = self._redact(ScrubMatch(path, value, candidate))
                if not _is_unchanged_value(value, result):
                    return result
                unchanged_matches += 1
                if unchanged_matches >= _MAX_UNCHANGED_MATCHES:
                    self.scrub_count += 1
                    return '[Scrubbed due to too many allowed matches]'
            # Keep overlapping matches at later starts visible, including after zero-width matches.
            next_position = match.start() + 1
            if next_position > len(text):
                return result
            next_match = self._pattern.search(text, next_position)
            if next_match is None:
                return result
            match = next_match

    def _redact(self, match: ScrubMatch) -> Any:
        result = None
        if self._callback:
            with handle_internal_errors:
                result = self._callback(match)
        if result is not None:
            if not _is_unchanged_value(match.value, result):
                self.scrub_count += 1
            return result
        self.scrub_count += 1
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
        if self.check_keys or field_name in self.scrubber.SAFE_KEYS:
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
