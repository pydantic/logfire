"""**Logfire** is the observability tool focused on developer experience."""

from __future__ import annotations

from typing import Any

from ._internal.auto_trace import AutoTraceModule
from ._internal.auto_trace.rewrite_ast import no_auto_trace
from ._internal.config import (
    METRICS_PREFERRED_TEMPORALITY,
    ConsoleOptions,
    PydanticPlugin,
    configure,
)
from ._internal.constants import LevelName
from ._internal.exporters.file import load_file as load_spans_from_file
from ._internal.main import Logfire, LogfireSpan
from ._internal.scrubbing import ScrubMatch
from ._internal.utils import suppress_instrumentation
from .integrations.logging import LogfireLoggingHandler
from .integrations.structlog import LogfireProcessor as StructlogProcessor
from .version import VERSION

DEFAULT_LOGFIRE_INSTANCE = Logfire()
span = DEFAULT_LOGFIRE_INSTANCE.span
instrument = DEFAULT_LOGFIRE_INSTANCE.instrument
force_flush = DEFAULT_LOGFIRE_INSTANCE.force_flush
log_slow_async_callbacks = DEFAULT_LOGFIRE_INSTANCE.log_slow_async_callbacks
install_auto_tracing = DEFAULT_LOGFIRE_INSTANCE.install_auto_tracing
instrument_fastapi = DEFAULT_LOGFIRE_INSTANCE.instrument_fastapi
instrument_openai = DEFAULT_LOGFIRE_INSTANCE.instrument_openai
instrument_anthropic = DEFAULT_LOGFIRE_INSTANCE.instrument_anthropic
instrument_asyncpg = DEFAULT_LOGFIRE_INSTANCE.instrument_asyncpg
instrument_httpx = DEFAULT_LOGFIRE_INSTANCE.instrument_httpx
instrument_requests = DEFAULT_LOGFIRE_INSTANCE.instrument_requests
instrument_psycopg = DEFAULT_LOGFIRE_INSTANCE.instrument_psycopg
instrument_django = DEFAULT_LOGFIRE_INSTANCE.instrument_django
instrument_flask = DEFAULT_LOGFIRE_INSTANCE.instrument_flask
instrument_starlette = DEFAULT_LOGFIRE_INSTANCE.instrument_starlette
instrument_aiohttp_client = DEFAULT_LOGFIRE_INSTANCE.instrument_aiohttp_client
instrument_sqlalchemy = DEFAULT_LOGFIRE_INSTANCE.instrument_sqlalchemy
instrument_redis = DEFAULT_LOGFIRE_INSTANCE.instrument_redis
instrument_pymongo = DEFAULT_LOGFIRE_INSTANCE.instrument_pymongo
shutdown = DEFAULT_LOGFIRE_INSTANCE.shutdown
with_tags = DEFAULT_LOGFIRE_INSTANCE.with_tags
# with_trace_sample_rate = DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate
with_settings = DEFAULT_LOGFIRE_INSTANCE.with_settings

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
metric_gauge = DEFAULT_LOGFIRE_INSTANCE.metric_gauge
metric_counter_callback = DEFAULT_LOGFIRE_INSTANCE.metric_counter_callback
metric_gauge_callback = DEFAULT_LOGFIRE_INSTANCE.metric_gauge_callback
metric_up_down_counter_callback = DEFAULT_LOGFIRE_INSTANCE.metric_up_down_counter_callback


def loguru_handler() -> dict[str, Any]:
    """Create a **Logfire** handler for Loguru.

    Returns:
        A dictionary with the handler and format for Loguru.
    """
    from .integrations import loguru

    return {'sink': loguru.LogfireHandler(), 'format': '{message}'}


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
    'VERSION',
    'suppress_instrumentation',
    'StructlogProcessor',
    'LogfireLoggingHandler',
)
