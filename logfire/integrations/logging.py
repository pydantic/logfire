"""Integration with the standard library logging module."""
from __future__ import annotations

from logging import Handler as LoggingHandler, LogRecord

from logfire import log
from logfire._constants import ATTRIBUTES_LOGGING_ARGS_KEY, ATTRIBUTES_MESSAGE_KEY

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
    """A logging handler that sends logs to Logfire.

    ```py
    from logging import basicConfig, getLogger

    from logfire.integrations.logging import LogfireLoggingHandler

    basicConfig(handlers=[LogfireLoggingHandler()])

    logger = getLogger(__name__)

    logger.error('{first_name=} failed!', extra={'first_name': 'Fred'})
    ```
    """

    def emit(self, record: LogRecord) -> None:
        """Send the log to Logfire.

        Args:
            record: The log record to send.
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

        log(
            msg_template=record.msg,  # type: ignore
            level=record.levelname.lower(),  # type: ignore
            attributes=attributes,
            custom_scope_suffix='stdlib.logging',
        )
