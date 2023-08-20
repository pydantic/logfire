from __future__ import annotations

from logging import Handler as LoggingHandler, LogRecord

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
)


class SpanLoggingHandler(LoggingHandler):
    def emit(self, record: LogRecord) -> None:
        log(
            record.msg,
            record.levelname.upper(),  # type: ignore
            **{k: v for k, v in record.__dict__.items() if k not in RESERVED_ATTRS},
        )
