from ._auto_instrument import install_automatic_instrumentation, uninstall_automatic_instrumentation
from ._config import configure
from ._flatten import flatten
from ._main import LevelName, Logfire, LogfireSpan
from .version import VERSION

DEFAULT_LOGFIRE_INSTANCE = Logfire()
tags = DEFAULT_LOGFIRE_INSTANCE.tags
span = DEFAULT_LOGFIRE_INSTANCE.span
instrument = DEFAULT_LOGFIRE_INSTANCE.instrument
log = DEFAULT_LOGFIRE_INSTANCE.log
debug = DEFAULT_LOGFIRE_INSTANCE.debug
info = DEFAULT_LOGFIRE_INSTANCE.info
notice = DEFAULT_LOGFIRE_INSTANCE.notice
warning = DEFAULT_LOGFIRE_INSTANCE.warning
error = DEFAULT_LOGFIRE_INSTANCE.error
critical = DEFAULT_LOGFIRE_INSTANCE.critical
force_flush = DEFAULT_LOGFIRE_INSTANCE.force_flush


__version__ = VERSION

__all__ = (
    'Logfire',
    'LogfireSpan',
    'LevelName',
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
    'install_automatic_instrumentation',
    'uninstall_automatic_instrumentation',
    'flatten',
    'force_flush',
    'tags',
)
