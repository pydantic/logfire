"""Logfire is the observability tool focused on developer experience."""

from ._auto_instrument import install_automatic_instrumentation, uninstall_automatic_instrumentation
from ._config import ConsoleOptions, configure
from ._flatten import flatten
from ._main import LevelName, Logfire, LogfireSpan
from .exporters._file import load_file as load_spans_from_file
from .version import VERSION

DEFAULT_LOGFIRE_INSTANCE = Logfire()
with_tags = DEFAULT_LOGFIRE_INSTANCE.with_tags
with_trace_sample_rate = DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate
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
    'ConsoleOptions',
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
    'with_tags',
    'with_trace_sample_rate',
    'load_spans_from_file',
)
