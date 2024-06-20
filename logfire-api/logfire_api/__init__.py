from __future__ import annotations

from contextlib import contextmanager
import importlib
import sys
from typing import TYPE_CHECKING, Literal
from unittest.mock import MagicMock

try:
    logfire_module = importlib.import_module('logfire')
    sys.modules[__name__] = logfire_module

except ImportError:
    if not TYPE_CHECKING:
        LevelName = Literal['trace', 'debug', 'info', 'notice', 'warn', 'warning', 'error', 'fatal']
        VERSION = '0.0.0'
        METRICS_PREFERRED_TEMPORALITY = {}

        def configure(*args, **kwargs): ...

        class LogfireSpan:
            def __getattr__(self, attr):
                return MagicMock()

            def __enter__(self):
                return self

            def __exit__(self, *args, **kwargs) -> None: ...

        class Logfire:
            def __getattr__(self, attr):
                return MagicMock()

            def __init__(self, *args, **kwargs) -> None: ...

            def span(self, *args, **kwargs) -> LogfireSpan:
                return LogfireSpan()

            def log(self, *args, **kwargs) -> None: ...

            def trace(self, *args, **kwargs) -> None: ...

            def debug(self, *args, **kwargs) -> None: ...

            def notice(self, *args, **kwargs) -> None: ...

            def info(self, *args, **kwargs) -> None: ...

            def warn(self, *args, **kwargs) -> None: ...

            def error(self, *args, **kwargs) -> None: ...

            def fatal(self, *args, **kwargs) -> None: ...

            def with_tags(self, *args, **kwargs) -> Logfire:
                return self

            def with_settings(self, *args, **kwargs) -> Logfire:
                return self

            def force_flush(self, *args, **kwargs) -> None: ...

            def log_slow_async_callbacks(self, *args, **kwargs) -> None: ...

            def install_auto_tracing(self, *args, **kwargs) -> None: ...

            def instrument(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

            def instrument_fastapi(self, *args, **kwargs) -> None: ...

            def instrument_pymongo(self, *args, **kwargs) -> None: ...

            def instrument_sqlalchemy(self, *args, **kwargs) -> None: ...

            def instrument_redis(self, *args, **kwargs) -> None: ...

            def instrument_flask(self, *args, **kwargs) -> None: ...

            def instrument_starlette(self, *args, **kwargs) -> None: ...

            def instrument_django(self, *args, **kwargs) -> None: ...

            def instrument_psycopg(self, *args, **kwargs) -> None: ...

            def instrument_requests(self, *args, **kwargs) -> None: ...

            def instrument_httpx(self, *args, **kwargs) -> None: ...

            def instrument_asyncpg(self, *args, **kwargs) -> None: ...

            def instrument_anthropic(self, *args, **kwargs) -> None: ...

            def instrument_openai(self, *args, **kwargs) -> None: ...

            def instrument_aiohttp_client(self, *args, **kwargs) -> None: ...

            def shutdown(self, *args, **kwargs) -> None: ...

        DEFAULT_LOGFIRE_INSTANCE = Logfire()
        span = DEFAULT_LOGFIRE_INSTANCE.span
        log = DEFAULT_LOGFIRE_INSTANCE.log
        trace = DEFAULT_LOGFIRE_INSTANCE.trace
        debug = DEFAULT_LOGFIRE_INSTANCE.debug
        notice = DEFAULT_LOGFIRE_INSTANCE.notice
        info = DEFAULT_LOGFIRE_INSTANCE.info
        warn = DEFAULT_LOGFIRE_INSTANCE.warn
        error = DEFAULT_LOGFIRE_INSTANCE.error
        fatal = DEFAULT_LOGFIRE_INSTANCE.fatal
        with_tags = DEFAULT_LOGFIRE_INSTANCE.with_tags
        with_settings = DEFAULT_LOGFIRE_INSTANCE.with_settings
        force_flush = DEFAULT_LOGFIRE_INSTANCE.force_flush
        log_slow_async_callbacks = DEFAULT_LOGFIRE_INSTANCE.log_slow_async_callbacks
        install_auto_tracing = DEFAULT_LOGFIRE_INSTANCE.install_auto_tracing
        instrument = DEFAULT_LOGFIRE_INSTANCE.instrument
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

        def no_auto_trace(x):
            return x

        @contextmanager
        def suppress_instrumentation():
            yield

        class ConsoleOptions:
            def __init__(self, *args, **kwargs) -> None: ...

        class PydanticPlugin:
            def __init__(self, *args, **kwargs) -> None: ...

        class ScrubMatch:
            def __init__(self, *args, **kwargs) -> None: ...

        class AutoTraceModule:
            def __init__(self, *args, **kwargs) -> None: ...

        class StructlogProcessor:
            def __init__(self, *args, **kwargs) -> None: ...

        class LogfireLoggingHandler:
            def __init__(self, *args, **kwargs) -> None: ...

        def load_spans_from_file(*args, **kwargs):
            return []
