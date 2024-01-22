"""Integration with the standard library logging module."""
from __future__ import annotations

from logging import Handler as LoggingHandler, LogRecord

from opentelemetry.context import detach

from logfire import log

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
    """A logging handler that sends logs to Logfire."""

    def emit(self, record: LogRecord) -> None:
        """Send the log to Logfire.

        Args:
            record: The log record to send.
        """
        attributes = {k: v for k, v in record.__dict__.items() if k not in RESERVED_ATTRS}
        attributes['code.filepath'] = record.pathname
        attributes['code.lineno'] = record.lineno
        attributes['code.function'] = record.funcName
        try:
            log(
                msg_template=record.msg,  # type: ignore
                level=record.levelname.lower(),  # type: ignore
                attributes=attributes,
            )
        finally:
            detach(id)
