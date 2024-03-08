"""**Logfire** is the observability tool focused on developer experience."""

from ._auto_trace import AutoTraceModule
from ._auto_trace.rewrite_ast import no_auto_trace
from ._config import METRICS_PREFERRED_TEMPORALITY, ConsoleOptions, PydanticPlugin, configure
from ._main import LevelName, Logfire, LogfireSpan
from ._scrubbing import ScrubMatch
from .exporters._file import load_file as load_spans_from_file
from .version import VERSION

DEFAULT_LOGFIRE_INSTANCE = Logfire()
with_tags = DEFAULT_LOGFIRE_INSTANCE.with_tags
# with_trace_sample_rate = DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate
span = DEFAULT_LOGFIRE_INSTANCE.span
instrument = DEFAULT_LOGFIRE_INSTANCE.instrument
force_flush = DEFAULT_LOGFIRE_INSTANCE.force_flush
log_slow_async_callbacks = DEFAULT_LOGFIRE_INSTANCE.log_slow_async_callbacks
install_auto_tracing = DEFAULT_LOGFIRE_INSTANCE.install_auto_tracing
instrument_fastapi = DEFAULT_LOGFIRE_INSTANCE.instrument_fastapi
shutdown = DEFAULT_LOGFIRE_INSTANCE.shutdown

# Logging
log = DEFAULT_LOGFIRE_INSTANCE.log
trace = DEFAULT_LOGFIRE_INSTANCE.trace
debug = DEFAULT_LOGFIRE_INSTANCE.debug
info = DEFAULT_LOGFIRE_INSTANCE.info
notice = DEFAULT_LOGFIRE_INSTANCE.notice
warn = DEFAULT_LOGFIRE_INSTANCE.warn
error = DEFAULT_LOGFIRE_INSTANCE.error
fatal = DEFAULT_LOGFIRE_INSTANCE.fatal
exception = DEFAULT_LOGFIRE_INSTANCE.exception

# Metrics
metric_counter = DEFAULT_LOGFIRE_INSTANCE.metric_counter
metric_histogram = DEFAULT_LOGFIRE_INSTANCE.metric_histogram
metric_up_down_counter = DEFAULT_LOGFIRE_INSTANCE.metric_up_down_counter
metric_counter_callback = DEFAULT_LOGFIRE_INSTANCE.metric_counter_callback
metric_gauge_callback = DEFAULT_LOGFIRE_INSTANCE.metric_gauge_callback
metric_up_down_counter_callback = DEFAULT_LOGFIRE_INSTANCE.metric_up_down_counter_callback


__version__ = VERSION

__all__ = (
    'Logfire',
    'LogfireSpan',
    'LevelName',
    'ConsoleOptions',
    'PydanticPlugin',
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
    'force_flush',
    'log_slow_async_callbacks',
    'install_auto_tracing',
    'instrument_fastapi',
    'AutoTraceModule',
    'with_tags',
    # 'with_trace_sample_rate',
    'load_spans_from_file',
    'no_auto_trace',
    'METRICS_PREFERRED_TEMPORALITY',
    'ScrubMatch',
)
