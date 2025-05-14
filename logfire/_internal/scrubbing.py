from __future__ import annotations

import copy
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence, TypedDict, cast

import typing_extensions
from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk._logs import LogRecord
from opentelemetry.sdk.trace import Event
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Link

from .constants import (
    ATTRIBUTES_JSON_SCHEMA_KEY,
    ATTRIBUTES_LOG_LEVEL_NAME_KEY,
    ATTRIBUTES_LOG_LEVEL_NUM_KEY,
    ATTRIBUTES_LOGGING_NAME,
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY,
    ATTRIBUTES_SAMPLE_RATE_KEY,
    ATTRIBUTES_SCRUBBED_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    ATTRIBUTES_TAGS_KEY,
    RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS,
)
from .stack_info import STACK_INFO_KEYS
from .utils import ReadableSpanDict

DEFAULT_PATTERNS = [
    'password',
    'passwd',
    'mysql_pwd',
    'secret',
    r'auth(?!ors?\b)',
    'credential',
    'private[._ -]?key',
    'api[._ -]?key',
    'session',
    'cookie',
    'social[._ -]?security',
    'credit[._ -]?card',
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
    """


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
        RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS,
        *STACK_INFO_KEYS,
        SpanAttributes.EXCEPTION_STACKTRACE,
        SpanAttributes.EXCEPTION_TYPE,
        SpanAttributes.EXCEPTION_MESSAGE,
        SpanAttributes.SCHEMA_URL,
        SpanAttributes.HTTP_METHOD,
        SpanAttributes.HTTP_STATUS_CODE,
        SpanAttributes.HTTP_SCHEME,
        SpanAttributes.HTTP_URL,
        SpanAttributes.HTTP_TARGET,
        SpanAttributes.HTTP_ROUTE,
        SpanAttributes.DB_STATEMENT,
        'db.plan',
        # Newer semantic conventions
        SpanAttributes.URL_FULL,
        SpanAttributes.URL_PATH,
        SpanAttributes.URL_QUERY,
        'event.name',
        'agent_session_id',
        'do_not_scrub',
        'binary_content',
    }

    @abstractmethod
    def scrub_span(self, span: ReadableSpanDict): ...  # pragma: no cover

    @abstractmethod
    def scrub_log(self, log: LogRecord) -> LogRecord: ...  # pragma: no cover

    @abstractmethod
    def scrub_value(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]: ...  # pragma: no cover


class NoopScrubber(BaseScrubber):
    def scrub_span(self, span: ReadableSpanDict):
        pass

    def scrub_log(self, log: LogRecord) -> LogRecord:
        return log

    def scrub_value(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]:  # pragma: no cover
        return value, []


NOOP_SCRUBBER = NoopScrubber()


class Scrubber(BaseScrubber):
    """Redacts potentially sensitive data."""

    def __init__(self, patterns: Sequence[str] | None, callback: ScrubCallback | None = None):
        # See ScrubbingOptions for more info on these parameters.
        patterns = [*DEFAULT_PATTERNS, *(patterns or [])]
        self._pattern = re.compile('|'.join(patterns), re.IGNORECASE | re.DOTALL)
        self._callback = callback

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


class SpanScrubber:
    """Does the actual scrubbing work.

    This class is separate from Scrubber so that it can be instantiated more regularly
    and hold and mutate state about the span being scrubbed, specifically the scrubbed notes.
    """

    def __init__(self, parent: Scrubber):
        self._pattern = parent._pattern  # type: ignore
        self._callback = parent._callback  # type: ignore
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

    def scrub(self, path: JsonPath, value: Any) -> Any:
        """Redacts sensitive data from `value`, recursing into nested sequences and mappings.

        `path` is a list of keys and indices leading to `value` in the span.
        Similar to the truncation code, it should use the field names in the frontend, e.g. `otel_events`.
        """
        if isinstance(value, str):
            if match := self._pattern.search(value):
                if match.span() == (0, len(value)):
                    # If the *whole* string matches, e.g. the value is literally 'password' and nothing more,
                    # it's considered safe.
                    return value
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    return self._redact(ScrubMatch(path, value, match))
                else:
                    return json.dumps(self.scrub(path, value))
        elif isinstance(value, Sequence):
            return [self.scrub(path + (i,), x) for i, x in enumerate(cast('Sequence[Any]', value))]
        elif isinstance(value, Mapping):
            result: dict[str, Any] = {}
            for k, v in cast('Mapping[str, Any]', value).items():
                if k in BaseScrubber.SAFE_KEYS:
                    result[k] = v
                elif match := self._pattern.search(k):
                    redacted = self._redact(ScrubMatch(path + (k,), v, match))
                    if isinstance(redacted, str) and isinstance(v, Sequence) and not isinstance(v, str):
                        redacted = [redacted]
                    result[k] = redacted
                else:
                    result[k] = self.scrub(path + (k,), v)
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
