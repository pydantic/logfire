"""Integration with the standard library logging module."""
from __future__ import annotations

from logging import Handler as LoggingHandler, LogRecord
from typing import Any, ClassVar

from logfire import log
from logfire._constants import ATTRIBUTES_LOGGING_ARGS_KEY, ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_MESSAGE_TEMPLATE_KEY

# skip natural LogRecord attributes
# http://docs.python.org/library/logging.html#logrecord-attributes
RESERVED_ATTRS: tuple[str, ...] = (
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
)


class LogfireLoggingHandler(LoggingHandler):
    """A logging handler that sends logs to **Logfire**."""

    custom_scope_suffix: ClassVar[str] = 'stdlib.logging'

    def emit(self, record: LogRecord) -> None:
        """Send the log to Logfire.

        Args:
            record: The log record to send.
        """
        attributes = self.fill_attributes(record)

        log(
            msg_template=attributes.pop(ATTRIBUTES_MESSAGE_TEMPLATE_KEY, record.msg),
            level=record.levelname.lower(),  # type: ignore
            attributes=attributes,
            custom_scope_suffix=self.custom_scope_suffix,
            exc_info=record.exc_info,
        )

    def fill_attributes(self, record: LogRecord) -> dict[str, Any]:
        """Fill the attributes to send to Logfire.

        This method can be overridden to add more attributes.

        Args:
            record: The log record.

        Returns:
            The attributes for the log record.
        """
        attributes = {k: v for k, v in record.__dict__.items() if k not in RESERVED_ATTRS}
        attributes['code.filepath'] = record.pathname
        attributes['code.lineno'] = record.lineno
        attributes['code.function'] = record.funcName

        # If there are args, we want to include them in the log message.
        if record.args:
            attributes[ATTRIBUTES_MESSAGE_KEY] = record.msg % record.args
            if isinstance(record.args, dict):
                attributes.update(record.args)
            else:
                attributes[ATTRIBUTES_LOGGING_ARGS_KEY] = record.args
        else:
            attributes[ATTRIBUTES_MESSAGE_KEY] = record.msg

        return attributes
