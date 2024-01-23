"""Logfire is the observability tool focused on developer experience."""

from ._auto_trace import AutoTraceModule, install_auto_tracing
from ._config import ConsoleOptions, PydanticPluginOptions, configure
from ._main import LevelName, Logfire, LogfireSpan
from .exporters._file import load_file as load_spans_from_file
from .version import VERSION

DEFAULT_LOGFIRE_INSTANCE = Logfire()
with_tags = DEFAULT_LOGFIRE_INSTANCE.with_tags
with_trace_sample_rate = DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate
span = DEFAULT_LOGFIRE_INSTANCE.span
instrument = DEFAULT_LOGFIRE_INSTANCE.instrument
log = DEFAULT_LOGFIRE_INSTANCE.log
trace = DEFAULT_LOGFIRE_INSTANCE.trace
debug = DEFAULT_LOGFIRE_INSTANCE.debug
info = DEFAULT_LOGFIRE_INSTANCE.info
notice = DEFAULT_LOGFIRE_INSTANCE.notice
warn = DEFAULT_LOGFIRE_INSTANCE.warn
error = DEFAULT_LOGFIRE_INSTANCE.error
fatal = DEFAULT_LOGFIRE_INSTANCE.fatal
force_flush = DEFAULT_LOGFIRE_INSTANCE.force_flush
log_slow_async_callbacks = DEFAULT_LOGFIRE_INSTANCE.log_slow_async_callbacks


__version__ = VERSION

__all__ = (
    'Logfire',
    'LogfireSpan',
    'LevelName',
    'ConsoleOptions',
    'PydanticPluginOptions',
    'configure',
    'span',
    'instrument',
    'log',
    'info',
    'debug',
    'notice',
    'warn',
    'error',
    'fatal',
    'install_auto_tracing',
    'AutoTraceModule',
    'force_flush',
    'with_tags',
    'with_trace_sample_rate',
    'load_spans_from_file',
)
