"""Integration with the standard library logging module."""

from __future__ import annotations

from collections.abc import Mapping
from copy import copy
from logging import CRITICAL, NOTSET, Handler as LoggingHandler, LogRecord, StreamHandler
from typing import TYPE_CHECKING, Any, ClassVar, cast

import logfire

from .._internal.constants import (
    ATTRIBUTES_LOGGING_ARGS_KEY,
    ATTRIBUTES_LOGGING_NAME,
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_TAGS_KEY,
    LOGGING_TO_OTEL_LEVEL_NUMBERS,
)
from .._internal.scrubbing import BaseScrubber
from .._internal.utils import is_instrumentation_suppressed

# skip natural LogRecord attributes
# http://docs.python.org/library/logging.html#logrecord-attributes
RESERVED_ATTRS: frozenset[str] = frozenset(
    [
        'args',
        'asctime',
        'created',
        'exc_info',
        'exc_text',
        'filename',
        'funcName',
        'levelname',
        'levelno',
        'lineno',
        'module',
        'msecs',
        'message',
        'msg',
        'name',
        'pathname',
        'process',
        'processName',
        'relativeCreated',
        'stack_info',
        'thread',
        'threadName',
        'taskName',  # 3.12+
    ]
)

if TYPE_CHECKING:
    from .. import Logfire


class LogfireLoggingHandler(LoggingHandler):
    """A [logging](../../integrations/logging.md) handler that sends logs to **Logfire**.

    Args:
        level: The threshold level for this handler. Logging messages which are less severe than *level* will be ignored.
        fallback: A fallback handler to use when [instrumentation is suppressed](../../how-to-guides/suppress.md#suppress-instrumentation).
        logfire_instance: The Logfire instance to use when emitting logs. Defaults to the default global instance.
        console_log: Whether logs from this handler are also printed to the console by Logfire.
            Set to `False` if another handler already prints them, to avoid duplicates.
            Defaults to the setting of `logfire_instance`.
    """

    custom_scope_suffix: ClassVar[str] = 'stdlib.logging'

    def __init__(
        self,
        level: int | str = NOTSET,
        fallback: LoggingHandler = StreamHandler(),
        logfire_instance: Logfire | None = None,
        console_log: bool | None = None,
    ) -> None:
        super().__init__(level=level)
        self.fallback = fallback
        self.logfire_instance = (logfire_instance or logfire.DEFAULT_LOGFIRE_INSTANCE).with_settings(
            custom_scope_suffix=self.custom_scope_suffix, console_log=console_log
        )

    def emit(self, record: LogRecord) -> None:
        """Send the log to Logfire.

        Args:
            record: The log record to send.
        """
        if is_instrumentation_suppressed():
            self.fallback.handle(record)
            return

        # Like the handlers in the standard library, report a failure (e.g. a message that can't be formatted
        # with its arguments) through `handleError` instead of raising from the application's logging call.
        try:
            attributes = self.fill_attributes(record)
            tags = attributes.pop(ATTRIBUTES_TAGS_KEY, None)
            if isinstance(tags, str):
                tags = (tags,)

            self.logfire_instance.log(
                msg_template=attributes.pop(ATTRIBUTES_MESSAGE_TEMPLATE_KEY, record.msg),
                level=LOGGING_TO_OTEL_LEVEL_NUMBERS.get(min(record.levelno, CRITICAL), record.levelno),
                attributes=attributes,
                tags=tags,
                exc_info=record.exc_info,
            )
        except Exception:
            # Scrub the arguments that `handleError` prints to stderr, as we do for exported logs.
            self.handleError(self._scrub_args(record))

    def _scrub_args(self, record: LogRecord) -> LogRecord:
        record = copy(record)
        try:
            scrub = self.logfire_instance.config.scrubber.scrub_value
            args = record.args
            # Scrub the values with the paths they have in the exported span, as a scrubbing callback can look at the path.
            if not isinstance(args, Mapping):
                record.args = tuple(scrub(('attributes', ATTRIBUTES_LOGGING_ARGS_KEY), args or ())[0])
            elif _is_single_positional_argument(record.msg, args):
                record.args = scrub(('attributes', ATTRIBUTES_LOGGING_ARGS_KEY), (args,))[0][0]
            else:
                record.args = scrub(('attributes',), dict(args))[0]
        except Exception:  # pragma: no cover
            # Never print arguments that couldn't be scrubbed.
            record.args = None
        return record

    def fill_attributes(self, record: LogRecord) -> dict[str, Any]:
        """Fill the attributes to send to Logfire.

        This method can be overridden to add more attributes or customize `logfire.msg_template`.

        Args:
            record: The log record.

        Returns:
            The attributes for the log record.
        """
        attributes = {k: v for k, v in record.__dict__.items() if k not in RESERVED_ATTRS}
        attributes['code.filepath'] = record.pathname
        attributes['code.lineno'] = record.lineno
        attributes['code.function'] = record.funcName
        attributes[ATTRIBUTES_LOGGING_NAME] = record.name

        attributes[ATTRIBUTES_MESSAGE_KEY], args = _format_message(record, self.logfire_instance.config.scrubber)
        attributes.update(args)
        attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] = record.msg

        return attributes


def _is_single_positional_argument(msg: Any, args: Mapping[str, Any]) -> bool:
    """Whether `_format_message` treats the mapping `args` as one positional argument, not as keyword arguments."""
    try:
        _ = msg % (args,)
    except TypeError:
        return False
    except Exception:
        pass  # The message can't be formatted either way, and `_format_message` fails with this error too.
    return True


def _scrub_container(scrubber: BaseScrubber, path: tuple[str | int, ...], value: Any) -> tuple[Any, bool]:
    """Scrub only containers; scalar strings and object string representations retain logging's behavior."""
    if not isinstance(value, (dict, list)):
        return value, False
    scrubbed, notes = scrubber.scrub_value(path, value)
    if notes:
        return scrubbed, True
    # A callback can replace a value without recording a scrub note. Ignore the scrubber's
    # tuple-to-list normalization when deciding whether the rendered message must change.
    return scrubbed, not _same_container_contents(value, scrubbed)


def _same_container_contents(original: Any, scrubbed: Any) -> bool:
    if isinstance(original, Mapping) and isinstance(scrubbed, Mapping):
        original_mapping = cast('Mapping[Any, Any]', original)
        scrubbed_mapping = cast('Mapping[Any, Any]', scrubbed)
        return original_mapping.keys() == scrubbed_mapping.keys() and all(
            _same_container_contents(original_mapping[key], scrubbed_mapping[key]) for key in original_mapping
        )
    if isinstance(original, (list, tuple)) and isinstance(scrubbed, (list, tuple)):
        original_sequence = cast('list[Any] | tuple[Any, ...]', original)
        scrubbed_sequence = cast('list[Any] | tuple[Any, ...]', scrubbed)
        return len(original_sequence) == len(scrubbed_sequence) and all(
            _same_container_contents(left, right) for left, right in zip(original_sequence, scrubbed_sequence)
        )
    try:
        return bool(original == scrubbed)
    except Exception:
        return False


def _format_message(record: LogRecord, scrubber: BaseScrubber) -> tuple[str, Mapping[str, Any]]:
    args = record.args
    msg = record.msg

    if not args:
        return msg, {}

    if type(args) is tuple:
        formatted = msg % args
        scrubbed_args = tuple(
            _scrub_container(scrubber, ('attributes', ATTRIBUTES_LOGGING_ARGS_KEY, i), arg)
            for i, arg in enumerate(args)
        )
        if any(changed for _, changed in scrubbed_args):
            formatted = msg % tuple(value for value, _ in scrubbed_args)
        return formatted, {ATTRIBUTES_LOGGING_ARGS_KEY: args}

    try:
        # args is a Mapping. Python extracted it from a tuple here:
        # https://github.com/python/cpython/blob/4c71d51a4b7989fc8754ba512c40e21666f9db0d/Lib/logging/__init__.py#L324-L326
        # Whether it should be treated as one positional argument or a mapping of keyword arguments
        # depends on the format string.
        # First check if the user wrote something like:
        #   log('Hello %s', {'name': 'Alice'})
        # in which case we should treat {'name': 'Alice'} as a single positional argument.
        formatted = msg % (args,)
    except TypeError:
        # This means the user wrote something like:
        #   log('Hello %(name)s', {'name': 'Alice'})
        # so `name` should be treated as a keyword argument, i.e. its own attribute.
        formatted = msg % args
        scrubbed_args, changed = _scrub_container(scrubber, ('attributes',), args)
        if changed:
            formatted = msg % scrubbed_args
        return formatted, cast('Mapping[str, Any]', args)
    else:
        # We have to wrap the single positional argument in a tuple.
        # Otherwise this:
        #   log('Hello %s', x)
        # would result in the shape of the data depending on whether x is a Mapping or not.
        scrubbed_arg, changed = _scrub_container(scrubber, ('attributes', ATTRIBUTES_LOGGING_ARGS_KEY, 0), args)
        if changed:
            formatted = msg % (scrubbed_arg,)
        return formatted, {ATTRIBUTES_LOGGING_ARGS_KEY: (args,)}
