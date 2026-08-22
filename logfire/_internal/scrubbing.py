from __future__ import annotations

import copy
import json
import re
import warnings
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import Any, TypedDict, cast

import typing_extensions
from opentelemetry._logs import LogRecord
from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk.trace import Event
from opentelemetry.trace import Link

from logfire.exceptions import LogfireConfigError

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


def _has_numeric_backreference(pattern: str) -> bool:
    r"""Whether `pattern` contains a backreference to a group by number, e.g. the `\1` in `(a)\1`.

    Escapes and character classes are tracked because `\1` inside `[...]` is an octal escape,
    and `\\1` is a literal backslash followed by a digit. Neither is a backreference.
    Three octal digits are an octal escape too, so `\123` is the character `S`, not a backreference.
    """
    in_class = False
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == '\\' and i + 1 < len(pattern):
            if not in_class and pattern[i + 1] in '123456789':
                escape = pattern[i + 1 : i + 4]
                if not (len(escape) == 3 and all(digit in '01234567' for digit in escape)):
                    return True
            i += 2
            continue
        if char == '[' and not in_class:
            in_class = True
            i += 1
            # A `]` at the very start of a class is a member of it rather than the end of it,
            # as in `[]a]`, and it may follow a negating `^`.
            if i < len(pattern) and pattern[i] == '^':
                i += 1
            if i < len(pattern) and pattern[i] == ']':
                i += 1
            continue
        if char == ']' and in_class:
            in_class = False
        i += 1
    return False


# Ordinary characters covering the classes a pattern is most likely to be written against.
# Only used if the minimum width can't be read from the parsed pattern, see below.
_ZERO_WIDTH_PROBE = 'aA0_ -.'


def _min_match_width(pattern: str) -> int | None:
    """The fewest characters `pattern` has to consume to match, or `None` if that can't be read.

    The regex parser knows this, but it lives in a private module which was named `sre_parse`
    before 3.11, so treat it as something that may not be there.
    """
    for module_name in ('re._parser', 'sre_parse'):
        try:
            parser = cast('Any', import_module(module_name))
        except ImportError:  # pragma: no cover
            continue

        try:
            return cast('tuple[int, int]', parser.parse(pattern).getwidth())[0]
        except Exception:  # pragma: no cover
            return None

    return None  # pragma: no cover


def _matches_without_consuming(compiled: re.Pattern[str]) -> bool:
    r"""Whether `compiled` can match without consuming any characters.

    Such a pattern reports a match on values containing nothing sensitive, so every value is
    redacted, with an empty string as the reason.

    The minimum width the pattern can match answers this exactly: it is 0 for `[0-9]*`, `\b` and
    `(?=x)`, and at least 1 for a pattern that has to consume something. If it can't be read,
    fall back to trying the pattern out: `search('')` covers the patterns matching the empty
    string outright, and the probe covers the ones needing a subject before they match an
    empty span, though it can't cover a subject the probe doesn't contain.
    """
    min_width = _min_match_width(compiled.pattern)
    if min_width is not None:  # pragma: no branch
        return min_width == 0

    if compiled.search('') is not None:  # pragma: no cover
        return True
    return any(match.group(0) == '' for match in compiled.finditer(_ZERO_WIDTH_PROBE))  # pragma: no cover


def _check_extra_patterns(patterns: Sequence[str] | None) -> list[str]:
    """Check user-supplied scrubbing patterns, raising `LogfireConfigError` on ones that can't work.

    The patterns are joined into a single regex, so a mistake in one of them changes the behaviour of
    the whole scrubber. Checking each pattern on its own here means the error can say which entry
    caused it, and means these mistakes fail at configuration time instead of silently either
    redacting everything or redacting nothing.

    The messages identify an entry by its index rather than quoting it, because a pattern may be a
    literal sensitive value, and an error raised at startup tends to end up in a log.
    """
    if patterns is None:
        return []

    if isinstance(patterns, str):
        # `str` satisfies `Sequence[str]`, so this type checks cleanly, and then iterating the string
        # turns 'password' into the alternation `p|a|s|s|w|o|r|d`, which matches nearly all text.
        raise LogfireConfigError(
            '`extra_patterns` must be a sequence of regular expressions, not a single string. '
            'A string is itself a sequence, so it would be read one character at a time. '
            'Wrap it in a list to pass a single pattern.'
        )

    checked: list[str] = []
    # Groups are numbered across the joined pattern in order, so only the groups that come before
    # an entry shift its own numbering. The default pattern uses non-capturing groups throughout,
    # but count it rather than assuming that stays true.
    preceding_groups = re.compile(_DEFAULT_PATTERN).groups

    for index, pattern in enumerate(patterns):
        entry = f'The `extra_patterns` entry at index {index}'

        if not isinstance(pattern, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise LogfireConfigError(f'{entry} is of type {type(pattern).__name__}, but it must be a string.')

        try:
            compiled = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        except re.error as e:
            # Compiling here rather than after joining means the position in the message refers to
            # this pattern, not to an offset within the combined pattern.
            raise LogfireConfigError(f'{entry} is not a valid regular expression: {e}') from e

        if _matches_without_consuming(compiled):
            raise LogfireConfigError(
                f'{entry} can match without consuming any characters, so it reports a match on values '
                f'containing nothing sensitive, which are then redacted with an empty reason. '
                f'A `*` where you meant `+`, or a look-around with nothing beside it, will do this.'
            )

        if preceding_groups and _has_numeric_backreference(pattern):
            # Only groups from earlier entries shift this one's numbering. With none of them, a
            # backreference still refers to this pattern's own group and works as written.
            raise LogfireConfigError(
                f'{entry} refers to a group by number, but {preceding_groups} capturing '
                f'{"group appears" if preceding_groups == 1 else "groups appear"} before it once the '
                f'patterns are combined into a single regex, so the numbering shifts and it would '
                f'point at the wrong group. Use a named group instead, e.g. `(?P<name>...)` and '
                f'`(?P=name)`, or make the earlier groups non-capturing with `(?:...)`.'
            )

        preceding_groups += compiled.groups
        checked.append(pattern)

    return checked


class Scrubber(BaseScrubber):
    """Redacts potentially sensitive data."""

    def __init__(self, patterns: Sequence[str] | None, callback: ScrubCallback | None = None):
        # See ScrubbingOptions for more info on these parameters.
        patterns = [_DEFAULT_PATTERN, *_check_extra_patterns(patterns)]
        try:
            with warnings.catch_warnings():
                # Before 3.11, a global flag away from the start of the expression was a
                # DeprecationWarning rather than an error, and it silently applies to every
                # pattern, the defaults included. Treat it the same way on every version.
                warnings.simplefilter('error', DeprecationWarning)
                self._pattern = re.compile('|'.join(patterns), re.IGNORECASE | re.DOTALL)
        except (re.error, DeprecationWarning) as e:
            # Entries that are each valid can still be invalid together, e.g. two of them using the
            # same group name, or one setting a global flag such as `(?i)` away from the start.
            raise LogfireConfigError(
                f'The `extra_patterns` entries are combined into a single regular expression, and '
                f'together they do not form a valid one: {e}. Two entries using the same group name, '
                f'or an inline flag such as `(?i)`, will do this. Note that patterns are always '
                f'matched case-insensitively.'
            ) from e
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
        self._pattern = parent._pattern  # pyright: ignore[reportPrivateUsage]
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
