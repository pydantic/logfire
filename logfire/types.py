from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from logfire._internal.constants import (
    ATTRIBUTES_LOG_LEVEL_NUM_KEY,
    LEVEL_NUMBERS,
    NUMBER_TO_LEVEL,
    LevelName,
    log_level_attributes,
)
from logfire._internal.tracer import get_parent_span
from logfire._internal.utils import canonicalize_exception_traceback

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan, Span


@dataclass
class SpanLevel:
    """A convenience class for comparing span/log levels.

    Can be compared to log level names (strings) such as 'info' or 'error' using
    `<`, `>`, `<=`, or `>=`, so e.g. `level >= 'error'` is valid.

    Will raise an exception if compared to a non-string or an invalid level name.
    """

    number: int
    """
    The raw numeric value of the level. Higher values are more severe.
    """

    @classmethod
    def from_span(cls, span: ReadableSpan) -> SpanLevel:
        """Create a SpanLevel from an OpenTelemetry span.

        If the span has no level set, defaults to 'info'.
        """
        attributes = span.attributes or {}
        level = attributes.get(ATTRIBUTES_LOG_LEVEL_NUM_KEY)
        if not isinstance(level, int):
            level = LEVEL_NUMBERS['info']
        return cls(level)

    @property
    def name(self) -> LevelName | None:
        """The human-readable name of the level, or `None` if the number is invalid."""
        return NUMBER_TO_LEVEL.get(self.number)

    def __eq__(self, other: object):
        if isinstance(other, int):
            return self.number == other
        if isinstance(other, str):
            return self.name == other
        if isinstance(other, SpanLevel):
            return self.number == other.number
        return NotImplemented

    def __hash__(self):
        return hash(self.number)

    def __lt__(self, other: LevelName):
        return self.number < LEVEL_NUMBERS[other]

    def __gt__(self, other: LevelName):
        return self.number > LEVEL_NUMBERS[other]

    def __ge__(self, other: LevelName):
        return self.number >= LEVEL_NUMBERS[other]

    def __le__(self, other: LevelName):
        return self.number <= LEVEL_NUMBERS[other]


@dataclass
class ExceptionCallbackHelper:
    """Helper object passed to the exception callback.

    This is experimental and may change significantly in future releases.
    """

    span: Span
    exception: BaseException
    _issue_fingerprint_source: str | None = None
    _create_issue: bool | None = None
    _record_exception: bool = True

    @property
    def level(self) -> SpanLevel:
        """Convenient way to see and compare the level of the span.

        Usually the level is error.
        FastAPI/Starlette 4xx HTTPExceptions are warnings.
        Will be a different level if this is created by e.g. `logfire.info(..., _exc_info=True)`.
        """
        return SpanLevel.from_span(self.span)

    @level.setter
    def level(self, value: LevelName | int) -> None:
        """Override the level of the span.

        For example:

            helper.level = 'warning'
        """
        self.span.set_attributes(log_level_attributes(value))

    @property
    def level_is_unset(self) -> bool:
        """Determine if the level has not been explicitly set on the span.

        This generally happens when a span is not marked as escaping.
        """
        return ATTRIBUTES_LOG_LEVEL_NUM_KEY not in (self.span.attributes or {})

    @property
    def parent_span(self) -> ReadableSpan | None:
        """The parent span of the span the exception was recorded on.

        This is `None` if there is no parent span, or if the parent span is in a different process.
        """
        return get_parent_span(self.span)

    @property
    def issue_fingerprint_source(self) -> str:
        """Returns a string that will be hashed to create the issue fingerprint.

        By default this is a canonical representation of the exception traceback.
        """
        if self._issue_fingerprint_source is not None:
            return self._issue_fingerprint_source
        self._issue_fingerprint_source = canonicalize_exception_traceback(self.exception)
        return self._issue_fingerprint_source

    @issue_fingerprint_source.setter
    def issue_fingerprint_source(self, value: str):
        """Override the string that will be hashed to create the issue fingerprint.

        For example, if you want all exceptions of a certain type to be grouped into the same issue,
        you could do something like:

            if isinstance(helper.exception, MyCustomError):
                helper.issue_fingerprint_source = "MyCustomError"

        Or if you want to add the exception message to make grouping more granular:

            helper.issue_fingerprint_source += str(helper.exception)

        Note that setting this property automatically sets `create_issue` to True.
        """
        self._issue_fingerprint_source = value
        self.create_issue = True

    @property
    def create_issue(self) -> bool:
        """Whether to create an issue for this exception.

        By default, issues are only created for exceptions on spans with level 'error' or higher,
        and for which no parent span exists in the current process.

        Example:
            if helper.create_issue:
                helper.issue_fingerprint_source = "MyCustomError"
        """
        if self._create_issue is not None:
            return self._create_issue

        # Note: the level might not be set if dealing with a non-escaping exception, but that's expected for e.g.
        # the root spans of web frameworks.
        return self._record_exception and (self.level_is_unset or self.level >= 'error') and self.parent_span is None

    @create_issue.setter
    def create_issue(self, value: bool):
        """Override whether to create an issue for this exception.

        For example, if you want to create issues for all exceptions, even warnings:

            helper.create_issue = True

        Issues can only be created if the exception is recorded on the span.
        """
        if not self._record_exception and value:
            raise ValueError('Cannot create issue if exception is not recorded on the span.')
        self._create_issue = value

    def no_record_exception(self) -> None:
        """Call this method to prevent recording the exception on the span.

        This improves performance and reduces noise in Logfire.
        This will also prevent creating an issue for this exception.
        The span itself will still be recorded, just without the exception information.
        This doesn't affect the level of the span, it will still be 'error' by default.
        """
        self._record_exception = False
        self._create_issue = False


ExceptionCallback = Callable[[ExceptionCallbackHelper], None]
"""
This is experimental and may change significantly in future releases.

Usage:

    def my_callback(helper: logfire.ExceptionCallbackHelper):
        ...

    logfire.configure(advanced=logfire.AdvancedOptions(exception_callback=my_callback))

Examples:

Set the level:

    helper.level = 'warning'

Make the issue fingerprint less granular:

    if isinstance(helper.exception, MyCustomError):
        helper.issue_fingerprint_source = "MyCustomError"

Make the issue fingerprint more granular:

    if helper.create_issue:
        helper.issue_fingerprint_source += str(helper.exception)

Create issues for all exceptions, even warnings:

    helper.create_issue = True

Don't record the exception on the span:

    helper.no_record_exception()
"""
