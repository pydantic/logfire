from __future__ import annotations

from logging import Handler as LoggingHandler, LogRecord

from opentelemetry.context import attach, detach, get_value, set_value

from logfire import log

from .._constants import SUPPRESS_INSTRUMENTATION_CONTEXT_KEY

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
    def emit(self, record: LogRecord) -> None:
        if get_value(SUPPRESS_INSTRUMENTATION_CONTEXT_KEY):
            return
        id = attach(set_value(SUPPRESS_INSTRUMENTATION_CONTEXT_KEY, True))
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
