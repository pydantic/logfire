from ._internal.auto_trace import AutoTraceModule as AutoTraceModule
from ._internal.auto_trace.rewrite_ast import no_auto_trace as no_auto_trace
from ._internal.config import AdvancedOptions as AdvancedOptions, CodeSource as CodeSource, ConsoleOptions as ConsoleOptions, MetricsOptions as MetricsOptions, PydanticPlugin as PydanticPlugin, configure as configure
from ._internal.constants import LevelName as LevelName
from ._internal.exporters.file import load_file as load_spans_from_file
from ._internal.main import Logfire as Logfire, LogfireSpan as LogfireSpan
from ._internal.scrubbing import ScrubMatch as ScrubMatch, ScrubbingOptions as ScrubbingOptions
from ._internal.utils import suppress_instrumentation as suppress_instrumentation
from .integrations.logging import LogfireLoggingHandler as LogfireLoggingHandler
from .integrations.structlog import LogfireProcessor as StructlogProcessor
from .version import VERSION as VERSION
from logfire.sampling import SamplingOptions as SamplingOptions
from typing import Any

__all__ = ['Logfire', 'LogfireSpan', 'LevelName', 'AdvancedOptions', 'ConsoleOptions', 'CodeSource', 'PydanticPlugin', 'configure', 'span', 'instrument', 'log', 'trace', 'debug', 'notice', 'info', 'warn', 'error', 'exception', 'fatal', 'force_flush', 'log_slow_async_callbacks', 'install_auto_tracing', 'instrument_asgi', 'instrument_wsgi', 'instrument_pydantic', 'instrument_fastapi', 'instrument_openai', 'instrument_anthropic', 'instrument_asyncpg', 'instrument_httpx', 'instrument_celery', 'instrument_requests', 'instrument_psycopg', 'instrument_django', 'instrument_flask', 'instrument_starlette', 'instrument_aiohttp_client', 'instrument_sqlalchemy', 'instrument_sqlite3', 'instrument_aws_lambda', 'instrument_redis', 'instrument_pymongo', 'instrument_mysql', 'instrument_system_metrics', 'AutoTraceModule', 'with_tags', 'with_settings', 'suppress_scopes', 'shutdown', 'load_spans_from_file', 'no_auto_trace', 'ScrubMatch', 'ScrubbingOptions', 'VERSION', 'suppress_instrumentation', 'StructlogProcessor', 'LogfireLoggingHandler', 'loguru_handler', 'SamplingOptions', 'MetricsOptions']

DEFAULT_LOGFIRE_INSTANCE = Logfire()
span = DEFAULT_LOGFIRE_INSTANCE.span
instrument = DEFAULT_LOGFIRE_INSTANCE.instrument
force_flush = DEFAULT_LOGFIRE_INSTANCE.force_flush
log_slow_async_callbacks = DEFAULT_LOGFIRE_INSTANCE.log_slow_async_callbacks
install_auto_tracing = DEFAULT_LOGFIRE_INSTANCE.install_auto_tracing
instrument_pydantic = DEFAULT_LOGFIRE_INSTANCE.instrument_pydantic
instrument_asgi = DEFAULT_LOGFIRE_INSTANCE.instrument_asgi
instrument_wsgi = DEFAULT_LOGFIRE_INSTANCE.instrument_wsgi
instrument_fastapi = DEFAULT_LOGFIRE_INSTANCE.instrument_fastapi
instrument_openai = DEFAULT_LOGFIRE_INSTANCE.instrument_openai
instrument_anthropic = DEFAULT_LOGFIRE_INSTANCE.instrument_anthropic
instrument_asyncpg = DEFAULT_LOGFIRE_INSTANCE.instrument_asyncpg
instrument_httpx = DEFAULT_LOGFIRE_INSTANCE.instrument_httpx
instrument_celery = DEFAULT_LOGFIRE_INSTANCE.instrument_celery
instrument_requests = DEFAULT_LOGFIRE_INSTANCE.instrument_requests
instrument_psycopg = DEFAULT_LOGFIRE_INSTANCE.instrument_psycopg
instrument_django = DEFAULT_LOGFIRE_INSTANCE.instrument_django
instrument_flask = DEFAULT_LOGFIRE_INSTANCE.instrument_flask
instrument_starlette = DEFAULT_LOGFIRE_INSTANCE.instrument_starlette
instrument_aiohttp_client = DEFAULT_LOGFIRE_INSTANCE.instrument_aiohttp_client
instrument_sqlalchemy = DEFAULT_LOGFIRE_INSTANCE.instrument_sqlalchemy
instrument_sqlite3 = DEFAULT_LOGFIRE_INSTANCE.instrument_sqlite3
instrument_aws_lambda = DEFAULT_LOGFIRE_INSTANCE.instrument_aws_lambda
instrument_redis = DEFAULT_LOGFIRE_INSTANCE.instrument_redis
instrument_pymongo = DEFAULT_LOGFIRE_INSTANCE.instrument_pymongo
instrument_mysql = DEFAULT_LOGFIRE_INSTANCE.instrument_mysql
instrument_system_metrics = DEFAULT_LOGFIRE_INSTANCE.instrument_system_metrics
suppress_scopes = DEFAULT_LOGFIRE_INSTANCE.suppress_scopes
shutdown = DEFAULT_LOGFIRE_INSTANCE.shutdown
with_tags = DEFAULT_LOGFIRE_INSTANCE.with_tags
with_settings = DEFAULT_LOGFIRE_INSTANCE.with_settings
log = DEFAULT_LOGFIRE_INSTANCE.log
trace = DEFAULT_LOGFIRE_INSTANCE.trace
debug = DEFAULT_LOGFIRE_INSTANCE.debug
info = DEFAULT_LOGFIRE_INSTANCE.info
notice = DEFAULT_LOGFIRE_INSTANCE.notice
warn = DEFAULT_LOGFIRE_INSTANCE.warn
error = DEFAULT_LOGFIRE_INSTANCE.error
fatal = DEFAULT_LOGFIRE_INSTANCE.fatal
exception = DEFAULT_LOGFIRE_INSTANCE.exception

def loguru_handler() -> Any:
    """Create a **Logfire** handler for Loguru.

    Returns:
        A dictionary with the handler and format for Loguru.
    """
__version__ = VERSION
