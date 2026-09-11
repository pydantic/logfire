from __future__ import annotations

import copy
import json
import re
import warnings
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any, TypedDict, cast

import typing_extensions
from opentelemetry._logs import LogRecord
from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk.trace import Event
from opentelemetry.trace import Link

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
    'logfire[._ -]?token',
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
_DEFAULT_PATTERN_START_CHARS = 'pmsacljx_'
_DEFAULT_PATTERN = rf'(?=[{_DEFAULT_PATTERN_START_CHARS}])(?:{"|".join(DEFAULT_PATTERNS)})'

_SCRUBBING_FLAGS = re.IGNORECASE | re.DOTALL

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

    @abstractmethod
    def scrub_span(self, span: ReadableSpanDict): ...

    @abstractmethod
    def scrub_log(self, log: LogRecord) -> LogRecord: ...

    @abstractmethod
    def scrub_value(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]: ...


class NoopScrubber(BaseScrubber):
    def scrub_span(self, span: ReadableSpanDict):
        pass

    def scrub_log(self, log: LogRecord) -> LogRecord:
        return log

    def scrub_value(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]:  # pragma: no cover
        return value, []


NOOP_SCRUBBER = NoopScrubber()


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile one pattern on its own, naming it if it's invalid.

    Compiling separately means the position in the error message points into the pattern
    the user actually wrote, instead of into the combined pattern they never see.
    """
    try:
        return re.compile(pattern, _SCRUBBING_FLAGS)
    except re.error as e:
        raise re.error(f'{e.msg} (in scrubbing pattern {pattern!r})', pattern, e.pos) from e


def _can_be_joined(pattern: str) -> bool:
    """Whether `pattern` still means the same thing after another pattern in an alternation.

    Global inline flags such as `(?s)` are only allowed at the very start of a pattern, so a pattern
    using them can't be combined with any other. Python 3.10 only warns about this, later versions
    raise, so turn that warning into an error to get the same answer everywhere. Any other warning
    is silenced: the pattern has already been compiled on its own, which is where the user should
    hear about it once.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            warnings.simplefilter('error', DeprecationWarning)
            re.compile(f'x|{pattern}', _SCRUBBING_FLAGS)
    except (re.error, DeprecationWarning):
        return False
    return True


def _compile_patterns(extra_patterns: Sequence[str] | None) -> list[re.Pattern[str]]:
    """Compile the default and extra patterns into as few regexes as possible.

    Patterns are combined into one alternation wherever that's safe, because one regex search
    is considerably cheaper than one per pattern on the short strings that most span attributes
    are made of.

    A pattern containing a capture group can't be combined: all patterns in an alternation share
    one group numbering space, so its groups would be renumbered, and a numeric backreference or
    conditional in it would then refer to a group belonging to another pattern. That pattern would
    silently never match, and data the user expected to be redacted would be exported. Giving such
    a pattern its own regex keeps its group numbering to itself, so it behaves as written.

    Only neighbouring patterns are combined, so the result stays in the configured order. Where two
    patterns match at the same position the earlier one has always won, and it still does.
    """
    compiled_patterns: list[re.Pattern[str]] = []
    joinable = [_DEFAULT_PATTERN]

    def flush_joinable():
        if joinable:
            with warnings.catch_warnings():
                # Each pattern has already been compiled on its own, which is where any warning
                # belongs: it names a position in the user's pattern, not in the combined one.
                warnings.simplefilter('ignore')
                compiled_patterns.append(re.compile('|'.join(joinable), _SCRUBBING_FLAGS))
            joinable.clear()

    for pattern in extra_patterns or []:
        compiled = _compile_pattern(pattern)
        if compiled.groups or not _can_be_joined(pattern):
            flush_joinable()
            compiled_patterns.append(compiled)
        else:
            joinable.append(pattern)
    flush_joinable()
    return compiled_patterns


def _leftmost_match(patterns: Sequence[re.Pattern[str]], value: str) -> re.Match[str] | None:
    """Find the leftmost match of any pattern, as a single combined pattern would.

    Where several patterns match at the same position the earliest one wins, which is also how
    `re` picks between the branches of an alternation.
    """
    best: re.Match[str] | None = None
    for pattern in patterns:
        match = pattern.search(value)
        if match and (best is None or match.start() < best.start()):
            best = match
            if best.start() == 0:  # No later pattern can match further left.
                break
    return best


class Scrubber(BaseScrubber):
    """Redacts potentially sensitive data."""

    def __init__(self, patterns: Sequence[str] | None, callback: ScrubCallback | None = None):
        # See ScrubbingOptions for more info on these parameters.
        self._patterns = _compile_patterns(patterns)
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
        patterns = parent._patterns  # pyright: ignore[reportPrivateUsage]
        # Runs for every attribute key and value, so call the single regex directly when there's only one.
        self._search: Callable[[str], re.Match[str] | None] = (
            patterns[0].search if len(patterns) == 1 else partial(_leftmost_match, patterns)
        )
        self._callback = parent._callback  # pyright: ignore[reportPrivateUsage]
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
            if match := self._search(value):
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
                elif match := self._search(k):
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
        if field_name not in self.scrubber.SAFE_KEYS:
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
