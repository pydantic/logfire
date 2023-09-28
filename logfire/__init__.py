from ._observe import Logfire, LogfireContext, LogfireSpan, TaggedLogfire
from .config import configure
from .version import VERSION

__version__ = VERSION

__all__ = (
    'Logfire',
    'LogfireContext',
    'LogfireSpan',
    'TaggedLogfire',
    'configure',
    'span',
    'instrument',
    'log',
    'info',
    'debug',
    'notice',
    'warning',
    'error',
    'critical',
    'context_tracer',
    'get_default_logger',
)

_default_logger = Logfire()

tags = _default_logger.tags

span = _default_logger.span
instrument = _default_logger.instrument

log = _default_logger.log
info = _default_logger.info
debug = _default_logger.debug
notice = _default_logger.notice
warning = _default_logger.warning
error = _default_logger.error
critical = _default_logger.critical

context_tracer = _default_logger.context_tracer


def get_default_logger() -> Logfire:
    return _default_logger
