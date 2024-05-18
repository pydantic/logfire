from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence, cast

from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk.trace import Event
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Link

from .constants import (
    ATTRIBUTES_JSON_SCHEMA_KEY,
    ATTRIBUTES_LOG_LEVEL_NAME_KEY,
    ATTRIBUTES_LOG_LEVEL_NUM_KEY,
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY,
    ATTRIBUTES_SAMPLE_RATE_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    ATTRIBUTES_TAGS_KEY,
    NULL_ARGS_KEY,
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
    'csrf',
    'xsrf',
    'jwt',
    'ssn',
    'social[._ -]?security',
    'credit[._ -]?card',
]


@dataclass
class ScrubMatch:
    """An object passed to the [`scrubbing_callback`][logfire.configure(scrubbing_callback)] function."""

    path: tuple[str | int, ...]
    """The path to the value in the span being considered for redaction, e.g. `('attributes', 'password')`."""

    value: Any
    """The value in the span being considered for redaction, e.g. `'my_password'`."""

    pattern_match: re.Match[str]
    """
    The regex match object indicating why the value is being redacted.
    Use `pattern_match.group(0)` to get the matched string.
    """


# See scrubbing_callback in logfire.configure for more info on this type.
ScrubCallback = Callable[[ScrubMatch], Any]


class Scrubber:
    """Redacts potentially sensitive data."""

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
        NULL_ARGS_KEY,
        RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS,
        *STACK_INFO_KEYS,
        SpanAttributes.EXCEPTION_STACKTRACE,  # See scrub_event_attributes
        SpanAttributes.EXCEPTION_TYPE,
        SpanAttributes.SCHEMA_URL,
        SpanAttributes.HTTP_METHOD,
        SpanAttributes.HTTP_STATUS_CODE,
        SpanAttributes.HTTP_SCHEME,
        SpanAttributes.HTTP_URL,
        SpanAttributes.HTTP_TARGET,
        SpanAttributes.HTTP_ROUTE,
        SpanAttributes.DB_STATEMENT,
        'db.plan',
    }

    def __init__(self, patterns: Sequence[str] | None, callback: ScrubCallback | None = None):
        # See scrubbing_patterns and scrubbing_callback in logfire.configure for more info on these parameters.
        patterns = [*DEFAULT_PATTERNS, *(patterns or [])]
        self._pattern = re.compile('|'.join(patterns), re.IGNORECASE | re.DOTALL)
        self._callback = callback

    def scrub_span(self, span: ReadableSpanDict):
        scope = span['instrumentation_scope']
        if scope and scope.name in ['logfire.openai', 'logfire.anthropic']:
            return

        # We need to use BoundedAttributes because:
        # 1. For events and links, we get an error otherwise:
        #      https://github.com/open-telemetry/opentelemetry-python/issues/3761
        # 2. The callback might return a value that isn't of the type required by OTEL,
        #      in which case BoundAttributes will discard it to prevent an error.
        # TODO silently throwing away the result is bad, and BoundedAttributes might be bad for performance.
        span['attributes'] = BoundedAttributes(attributes=self.scrub(('attributes',), span['attributes']))
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

    def scrub_event_attributes(self, event: Event, index: int):
        attributes = event.attributes or {}
        path = ('otel_events', index, 'attributes')
        new_attributes = self.scrub(path, attributes)

        # The traceback is likely to be full of false positives since it contains a lot of code and filenames.
        # We want to keep all of it except maybe the exception message at the end,
        # which may actually contain sensitive data.
        # If `old_message != new_message` then that means it was redacted,
        # so it needs to be replaced in the stacktrace.
        # Note that EXCEPTION_STACKTRACE is in SAFE_KEYS, but EXCEPTION_MESSAGE is not.
        # TODO this algorithm is not perfect. In particular it doesn't handle chained exceptions.
        #   The best solution would probably be to intercept `Span.record_exception` and format the stacktrace manually.
        if (stacktrace := attributes.get(SpanAttributes.EXCEPTION_STACKTRACE)) and (
            (old_message := attributes.get(SpanAttributes.EXCEPTION_MESSAGE))
            != (new_message := new_attributes.get(SpanAttributes.EXCEPTION_MESSAGE))
            and isinstance(stacktrace, str)
            and isinstance(old_message, str)
            and isinstance(new_message, str)
        ):
            stacktrace = stacktrace.rstrip()
            old_message = old_message.rstrip()
            if stacktrace.endswith(old_message):
                new_attributes[SpanAttributes.EXCEPTION_STACKTRACE] = stacktrace[: -len(old_message)] + new_message
            else:
                # The stacktrace doesn't look like we expect, so scrub the whole thing.
                new_attributes[SpanAttributes.EXCEPTION_STACKTRACE] = self.scrub(
                    path + (SpanAttributes.EXCEPTION_STACKTRACE,), stacktrace
                )

        return new_attributes

    def scrub(self, path: tuple[str | int, ...], value: Any) -> Any:
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
                if k in self.SAFE_KEYS:
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
            return result
        return f'[Redacted due to {match.pattern_match.group(0)!r}]'
