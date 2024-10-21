import anthropic
import openai
import opentelemetry.trace as trace_api
from . import async_ as async_
from ..version import VERSION as VERSION
from .auto_trace import AutoTraceModule as AutoTraceModule, install_auto_tracing as install_auto_tracing
from .config import GLOBAL_CONFIG as GLOBAL_CONFIG, LogfireConfig as LogfireConfig, OPEN_SPANS as OPEN_SPANS
from .config_params import PydanticPluginRecordValues as PydanticPluginRecordValues
from .constants import ATTRIBUTES_JSON_SCHEMA_KEY as ATTRIBUTES_JSON_SCHEMA_KEY, ATTRIBUTES_LOG_LEVEL_NUM_KEY as ATTRIBUTES_LOG_LEVEL_NUM_KEY, ATTRIBUTES_MESSAGE_KEY as ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_MESSAGE_TEMPLATE_KEY as ATTRIBUTES_MESSAGE_TEMPLATE_KEY, ATTRIBUTES_SAMPLE_RATE_KEY as ATTRIBUTES_SAMPLE_RATE_KEY, ATTRIBUTES_SPAN_TYPE_KEY as ATTRIBUTES_SPAN_TYPE_KEY, ATTRIBUTES_TAGS_KEY as ATTRIBUTES_TAGS_KEY, ATTRIBUTES_VALIDATION_ERROR_KEY as ATTRIBUTES_VALIDATION_ERROR_KEY, DISABLE_CONSOLE_KEY as DISABLE_CONSOLE_KEY, LEVEL_NUMBERS as LEVEL_NUMBERS, LevelName as LevelName, NULL_ARGS_KEY as NULL_ARGS_KEY, OTLP_MAX_INT_SIZE as OTLP_MAX_INT_SIZE, log_level_attributes as log_level_attributes
from .formatter import logfire_format as logfire_format, logfire_format_with_magic as logfire_format_with_magic
from .instrument import LogfireArgs as LogfireArgs, instrument as instrument
from .integrations.asyncpg import AsyncPGInstrumentKwargs as AsyncPGInstrumentKwargs
from .integrations.celery import CeleryInstrumentKwargs as CeleryInstrumentKwargs
from .integrations.flask import FlaskInstrumentKwargs as FlaskInstrumentKwargs
from .integrations.httpx import HTTPXInstrumentKwargs as HTTPXInstrumentKwargs
from .integrations.mysql import MySQLConnection as MySQLConnection, MySQLInstrumentKwargs as MySQLInstrumentKwargs
from .integrations.psycopg import PsycopgInstrumentKwargs as PsycopgInstrumentKwargs
from .integrations.pymongo import PymongoInstrumentKwargs as PymongoInstrumentKwargs
from .integrations.redis import RedisInstrumentKwargs as RedisInstrumentKwargs
from .integrations.sqlalchemy import SQLAlchemyInstrumentKwargs as SQLAlchemyInstrumentKwargs
from .integrations.starlette import StarletteInstrumentKwargs as StarletteInstrumentKwargs
from .integrations.system_metrics import Base as SystemMetricsBase, Config as SystemMetricsConfig
from .json_encoder import logfire_json_dumps as logfire_json_dumps
from .json_schema import JsonSchemaProperties as JsonSchemaProperties, attributes_json_schema as attributes_json_schema, attributes_json_schema_properties as attributes_json_schema_properties, create_json_schema as create_json_schema
from .metrics import ProxyMeterProvider as ProxyMeterProvider
from .stack_info import get_user_stack_info as get_user_stack_info
from .tracer import ProxyTracerProvider as ProxyTracerProvider
from .utils import SysExcInfo as SysExcInfo, get_version as get_version, handle_internal_errors as handle_internal_errors, log_internal_error as log_internal_error, uniquify_sequence as uniquify_sequence
from django.http import HttpRequest as HttpRequest, HttpResponse as HttpResponse
from fastapi import FastAPI
from flask.app import Flask
from opentelemetry.metrics import CallbackT as CallbackT, Counter, Histogram, UpDownCounter, _Gauge as Gauge
from opentelemetry.sdk.trace import ReadableSpan, Span as Span
from opentelemetry.trace import Tracer
from opentelemetry.util import types as otel_types
from starlette.applications import Starlette
from starlette.requests import Request as Request
from starlette.websockets import WebSocket as WebSocket
from typing import Any, Callable, ContextManager, Iterable, Literal, Sequence, TypeVar
from typing_extensions import LiteralString, ParamSpec, Unpack

ExcInfo = SysExcInfo | BaseException | bool | None

class Logfire:
    """The main logfire class."""
    def __init__(self, *, config: LogfireConfig = ..., sample_rate: float | None = None, tags: Sequence[str] = (), console_log: bool = True, otel_scope: str = 'logfire') -> None: ...
    @property
    def config(self) -> LogfireConfig: ...
    def trace(self, msg_template: str, /, *, _tags: Sequence[str] | None = None, _exc_info: ExcInfo = False, **attributes: Any) -> None:
        """Log a trace message.

        ```py
        import logfire

        logfire.configure()

        logfire.trace('This is a trace log')
        ```

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.
            _tags: An optional sequence of tags to include in the log.
            _exc_info: Set to an exception or a tuple as returned by [`sys.exc_info()`][sys.exc_info]
                to record a traceback with the log message.

                Set to `True` to use the currently handled exception.
        """
    def debug(self, msg_template: str, /, *, _tags: Sequence[str] | None = None, _exc_info: ExcInfo = False, **attributes: Any) -> None:
        """Log a debug message.

        ```py
        import logfire

        logfire.configure()

        logfire.debug('This is a debug log')
        ```

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.
            _tags: An optional sequence of tags to include in the log.
            _exc_info: Set to an exception or a tuple as returned by [`sys.exc_info()`][sys.exc_info]
                to record a traceback with the log message.

                Set to `True` to use the currently handled exception.
        """
    def info(self, msg_template: str, /, *, _tags: Sequence[str] | None = None, _exc_info: ExcInfo = False, **attributes: Any) -> None:
        """Log an info message.

        ```py
        import logfire

        logfire.configure()

        logfire.info('This is an info log')
        ```

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.
            _tags: An optional sequence of tags to include in the log.
            _exc_info: Set to an exception or a tuple as returned by [`sys.exc_info()`][sys.exc_info]
                to record a traceback with the log message.

                Set to `True` to use the currently handled exception.
        """
    def notice(self, msg_template: str, /, *, _tags: Sequence[str] | None = None, _exc_info: ExcInfo = False, **attributes: Any) -> None:
        """Log a notice message.

        ```py
        import logfire

        logfire.configure()

        logfire.notice('This is a notice log')
        ```

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.
            _tags: An optional sequence of tags to include in the log.
            _exc_info: Set to an exception or a tuple as returned by [`sys.exc_info()`][sys.exc_info]
                to record a traceback with the log message.

                Set to `True` to use the currently handled exception.
        """
    def warn(self, msg_template: str, /, *, _tags: Sequence[str] | None = None, _exc_info: ExcInfo = False, **attributes: Any) -> None:
        """Log a warning message.

        ```py
        import logfire

        logfire.configure()

        logfire.warn('This is a warning log')
        ```

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.
            _tags: An optional sequence of tags to include in the log.
            _exc_info: Set to an exception or a tuple as returned by [`sys.exc_info()`][sys.exc_info]
                to record a traceback with the log message.

                Set to `True` to use the currently handled exception.
        """
    def error(self, msg_template: str, /, *, _tags: Sequence[str] | None = None, _exc_info: ExcInfo = False, **attributes: Any) -> None:
        """Log an error message.

        ```py
        import logfire

        logfire.configure()

        logfire.error('This is an error log')
        ```

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.
            _tags: An optional sequence of tags to include in the log.
            _exc_info: Set to an exception or a tuple as returned by [`sys.exc_info()`][sys.exc_info]
                to record a traceback with the log message.

                Set to `True` to use the currently handled exception.
        """
    def fatal(self, msg_template: str, /, *, _tags: Sequence[str] | None = None, _exc_info: ExcInfo = False, **attributes: Any) -> None:
        """Log a fatal message.

        ```py
        import logfire

        logfire.configure()

        logfire.fatal('This is a fatal log')
        ```

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.
            _tags: An optional sequence of tags to include in the log.
            _exc_info: Set to an exception or a tuple as returned by [`sys.exc_info()`][sys.exc_info]
                to record a traceback with the log message.

                Set to `True` to use the currently handled exception.
        """
    def exception(self, msg_template: str, /, *, _tags: Sequence[str] | None = None, _exc_info: ExcInfo = True, **attributes: Any) -> None:
        """The same as `error` but with `_exc_info=True` by default.

        This means that a traceback will be logged for any currently handled exception.

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.
            _tags: An optional sequence of tags to include in the log.
            _exc_info: Set to an exception or a tuple as returned by [`sys.exc_info()`][sys.exc_info]
                to record a traceback with the log message.
        """
    def span(self, msg_template: str, /, *, _tags: Sequence[str] | None = None, _span_name: str | None = None, _level: LevelName | None = None, **attributes: Any) -> LogfireSpan:
        """Context manager for creating a span.

        ```py
        import logfire

        logfire.configure()

        with logfire.span('This is a span {a=}', a='data'):
            logfire.info('new log 1')
        ```

        Args:
            msg_template: The template for the span message.
            _span_name: The span name. If not provided, the `msg_template` will be used.
            _tags: An optional sequence of tags to include in the span.
            _level: An optional log level name.
            attributes: The arguments to include in the span and format the message template with.
                Attributes starting with an underscore are not allowed.
        """
    def instrument(self, msg_template: LiteralString | None = None, *, span_name: str | None = None, extract_args: bool = True) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Decorator for instrumenting a function as a span.

        ```py
        import logfire

        logfire.configure()


        @logfire.instrument('This is a span {a=}')
        def my_function(a: int):
            logfire.info('new log {a=}', a=a)
        ```

        !!! note
            - This decorator MUST be applied first, i.e. UNDER any other decorators.
            - The source code of the function MUST be accessible.

        Args:
            msg_template: The template for the span message. If not provided, the module and function name will be used.
            span_name: The span name. If not provided, the `msg_template` will be used.
            extract_args: Whether to extract arguments from the function signature and log them as span attributes.
        """
    def log(self, level: LevelName | int, msg_template: str, attributes: dict[str, Any] | None = None, tags: Sequence[str] | None = None, exc_info: ExcInfo = False, console_log: bool | None = None) -> None:
        """Log a message.

        ```py
        import logfire

        logfire.configure()

        logfire.log('info', 'This is a log {a}', {'a': 'Apple'})
        ```

        Args:
            level: The level of the log.
            msg_template: The message to log.
            attributes: The attributes to bind to the log.
            tags: An optional sequence of tags to include in the log.
            exc_info: Set to an exception or a tuple as returned by [`sys.exc_info()`][sys.exc_info]
                to record a traceback with the log message.

                Set to `True` to use the currently handled exception.
            console_log: Whether to log to the console, defaults to `True`.
        """
    def with_tags(self, *tags: str) -> Logfire:
        """A new Logfire instance which always uses the given tags.

        ```py
        import logfire

        logfire.configure()

        local_logfire = logfire.with_tags('tag1')
        local_logfire.info('a log message', _tags=['tag2'])

        # This is equivalent to:
        logfire.info('a log message', _tags=['tag1', 'tag2'])
        ```

        Args:
            tags: The tags to add.

        Returns:
            A new Logfire instance with the `tags` added to any existing tags.
        """
    def with_trace_sample_rate(self, sample_rate: float) -> Logfire:
        """A new Logfire instance with the given sampling ratio applied.

        Args:
            sample_rate: The sampling ratio to use.

        Returns:
            A new Logfire instance with the sampling ratio applied.
        """
    def with_settings(self, *, tags: Sequence[str] = (), stack_offset: int | None = None, console_log: bool | None = None, custom_scope_suffix: str | None = None) -> Logfire:
        """A new Logfire instance which uses the given settings.

        Args:
            tags: Sequence of tags to include in the log.
            stack_offset: The stack level offset to use when collecting stack info, also affects the warning which
                message formatting might emit, defaults to `0` which means the stack info will be collected from the
                position where [`logfire.log`][logfire.Logfire.log] was called.
            console_log: Whether to log to the console, defaults to `True`.
            custom_scope_suffix: A custom suffix to append to `logfire.` e.g. `logfire.loguru`.

                It should only be used when instrumenting another library with Logfire, such as structlog or loguru.

                See the `instrumenting_module_name` parameter on
                [TracerProvider.get_tracer][opentelemetry.sdk.trace.TracerProvider.get_tracer] for more info.

        Returns:
            A new Logfire instance with the given settings applied.
        """
    def force_flush(self, timeout_millis: int = 3000) -> bool:
        """Force flush all spans and metrics.

        Args:
            timeout_millis: The timeout in milliseconds.

        Returns:
            Whether the flush of spans was successful.
        """
    def log_slow_async_callbacks(self, slow_duration: float = 0.1) -> ContextManager[None]:
        """Log a warning whenever a function running in the asyncio event loop blocks for too long.

        This works by patching the `asyncio.events.Handle._run` method.

        Args:
            slow_duration: the threshold in seconds for when a callback is considered slow.

        Returns:
            A context manager that will revert the patch when exited.
                This context manager doesn't take into account threads or other concurrency.
                Calling this method will immediately apply the patch
                without waiting for the context manager to be opened,
                i.e. it's not necessary to use this as a context manager.
        """
    def install_auto_tracing(self, modules: Sequence[str] | Callable[[AutoTraceModule], bool], *, min_duration: float, check_imported_modules: Literal['error', 'warn', 'ignore'] = 'error') -> None:
        """Install automatic tracing.

        See the [Auto-Tracing guide](https://logfire.pydantic.dev/docs/guides/onboarding_checklist/add_auto_tracing/)
        for more info.

        This will trace all non-generator function calls in the modules specified by the modules argument.
        It's equivalent to wrapping the body of every function in matching modules in `with logfire.span(...):`.

        !!! note
            This function MUST be called before any of the modules to be traced are imported.

            Generator functions will not be traced for reasons explained [here](https://logfire.pydantic.dev/docs/guides/advanced/generators/).

        This works by inserting a new meta path finder into `sys.meta_path`, so inserting another finder before it
        may prevent it from working.

        It relies on being able to retrieve the source code via at least one other existing finder in the meta path,
        so it may not work if standard finders are not present or if the source code is not available.
        A modified version of the source code is then compiled and executed in place of the original module.

        Args:
            modules: List of module names to trace, or a function which returns True for modules that should be traced.
                If a list is provided, any submodules within a given module will also be traced.
            min_duration: A minimum duration in seconds for which a function must run before it's traced.
                Setting to `0` causes all functions to be traced from the beginning.
                Otherwise, the first time(s) each function is called, it will be timed but not traced.
                Only after the function has run for at least `min_duration` will it be traced in subsequent calls.
            check_imported_modules: If this is `'error'` (the default), then an exception will be raised if any of the
                modules in `sys.modules` (i.e. modules that have already been imported) match the modules to trace.
                Set to `'warn'` to issue a warning instead, or `'ignore'` to skip the check.
        """
    def instrument_pydantic(self, record: PydanticPluginRecordValues = 'all', include: Iterable[str] = (), exclude: Iterable[str] = ()) -> None:
        """Instrument Pydantic model validations.

        This must be called before defining and importing the model classes you want to instrument.
        See the [Pydantic integration guide](https://logfire.pydantic.dev/docs/integrations/pydantic/) for more info.

        Args:
            record: The record mode for the Pydantic plugin. It can be one of the following values:

                - `all`: Send traces and metrics for all events. This is default value.
                - `failure`: Send metrics for all validations and traces only for validation failures.
                - `metrics`: Send only metrics.
                - `off`: Disable instrumentation.
            include:
                By default, third party modules are not instrumented. This option allows you to include specific modules.
            exclude:
                Exclude specific modules from instrumentation.
        """
    def instrument_fastapi(self, app: FastAPI, *, capture_headers: bool = False, request_attributes_mapper: Callable[[Request | WebSocket, dict[str, Any]], dict[str, Any] | None] | None = None, use_opentelemetry_instrumentation: bool = True, excluded_urls: str | Iterable[str] | None = None, record_send_receive: bool = False, **opentelemetry_kwargs: Any) -> ContextManager[None]:
        """Instrument a FastAPI app so that spans and logs are automatically created for each request.

        Args:
            app: The FastAPI app to instrument.
            capture_headers: Set to `True` to capture all request and response headers.
            request_attributes_mapper: A function that takes a [`Request`][fastapi.Request] or [`WebSocket`][fastapi.WebSocket]
                and a dictionary of attributes and returns a new dictionary of attributes.
                The input dictionary will contain:

                - `values`: A dictionary mapping argument names of the endpoint function to parsed and validated values.
                - `errors`: A list of validation errors for any invalid inputs.

                The returned dictionary will be used as the attributes for a log message.
                If `None` is returned, no log message will be created.

                You can use this to e.g. only log validation errors, or nothing at all.
                You can also add custom attributes.

                The default implementation will return the input dictionary unchanged.
                The function mustn't modify the contents of `values` or `errors`.
            excluded_urls: A string of comma-separated regexes which will exclude a request from tracing if the full URL
                matches any of the regexes. This applies to both the Logfire and OpenTelemetry instrumentation.
                If not provided, the environment variables
                `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` and `OTEL_PYTHON_EXCLUDED_URLS` will be checked.
            use_opentelemetry_instrumentation: If True (the default) then
                [`FastAPIInstrumentor`][opentelemetry.instrumentation.fastapi.FastAPIInstrumentor]
                will also instrument the app.

                See [OpenTelemetry FastAPI Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html).
            record_send_receive: Set to True to allow the OpenTelemetry ASGI to create send/receive spans.
                These are disabled by default to reduce overhead and the number of spans created,
                since many can be created for a single request, and they are not often useful.
                If enabled, they will be set to debug level, meaning they will usually still be hidden in the UI.
            opentelemetry_kwargs: Additional keyword arguments to pass to the OpenTelemetry FastAPI instrumentation.

        Returns:
            A context manager that will revert the instrumentation when exited.
                This context manager doesn't take into account threads or other concurrency.
                Calling this method will immediately apply the instrumentation
                without waiting for the context manager to be opened,
                i.e. it's not necessary to use this as a context manager.
        """
    def instrument_openai(self, openai_client: openai.OpenAI | openai.AsyncOpenAI | type[openai.OpenAI] | type[openai.AsyncOpenAI] | None = None, *, suppress_other_instrumentation: bool = True) -> ContextManager[None]:
        """Instrument an OpenAI client so that spans are automatically created for each request.

        The following methods are instrumented for both the sync and the async clients:

        - [`client.chat.completions.create`](https://platform.openai.com/docs/guides/text-generation/chat-completions-api) — with and without `stream=True`
        - [`client.completions.create`](https://platform.openai.com/docs/guides/text-generation/completions-api) — with and without `stream=True`
        - [`client.embeddings.create`](https://platform.openai.com/docs/guides/embeddings/how-to-get-embeddings)
        - [`client.images.generate`](https://platform.openai.com/docs/guides/images/generations)

        When `stream=True` a second span is created to instrument the streamed response.

        Example usage:

        ```python
        import logfire
        import openai

        client = openai.OpenAI()
        logfire.configure()
        logfire.instrument_openai(client)

        response = client.chat.completions.create(
            model='gpt-4',
            messages=[
                {'role': 'system', 'content': 'You are a helpful assistant.'},
                {'role': 'user', 'content': 'What is four plus five?'},
            ],
        )
        print('answer:', response.choices[0].message.content)
        ```

        Args:
            openai_client: The OpenAI client or class to instrument:

                - `None` (the default) to instrument both the `openai.OpenAI` and `openai.AsyncOpenAI` classes.
                - The `openai.OpenAI` class or a subclass
                - The `openai.AsyncOpenAI` class or a subclass
                - An instance of `openai.OpenAI`
                - An instance of `openai.AsyncOpenAI`

            suppress_other_instrumentation: If True, suppress any other OTEL instrumentation that may be otherwise
                enabled. In reality, this means the HTTPX instrumentation, which could otherwise be called since
                OpenAI uses HTTPX to make HTTP requests.

        Returns:
            A context manager that will revert the instrumentation when exited.
                Use of this context manager is optional.
        """
    def instrument_anthropic(self, anthropic_client: anthropic.Anthropic | anthropic.AsyncAnthropic | type[anthropic.Anthropic] | type[anthropic.AsyncAnthropic] | None = None, *, suppress_other_instrumentation: bool = True) -> ContextManager[None]:
        """Instrument an Anthropic client so that spans are automatically created for each request.

        The following methods are instrumented for both the sync and the async clients:

        - [`client.messages.create`](https://docs.anthropic.com/en/api/messages)
        - [`client.messages.stream`](https://docs.anthropic.com/en/api/messages-streaming)
        - [`client.beta.tools.messages.create`](https://docs.anthropic.com/en/docs/tool-use)

        When `stream=True` a second span is created to instrument the streamed response.

        Example usage:

        ```python
        import logfire
        import anthropic

        client = anthropic.Anthropic()
        logfire.configure()
        logfire.instrument_anthropic(client)

        response = client.messages.create(
            model='claude-3-haiku-20240307',
            system='You are a helpful assistant.',
            messages=[
                {'role': 'user', 'content': 'What is four plus five?'},
            ],
        )
        print('answer:', response.content[0].text)
        ```

        Args:
            anthropic_client: The Anthropic client or class to instrument:

                - `None` (the default) to instrument both the
                    `anthropic.Anthropic` and `anthropic.AsyncAnthropic` classes.
                - The `anthropic.Anthropic` class or a subclass
                - The `anthropic.AsyncAnthropic` class or a subclass
                - An instance of `anthropic.Anthropic`
                - An instance of `anthropic.AsyncAnthropic`

            suppress_other_instrumentation: If True, suppress any other OTEL instrumentation that may be otherwise
                enabled. In reality, this means the HTTPX instrumentation, which could otherwise be called since
                OpenAI uses HTTPX to make HTTP requests.

        Returns:
            A context manager that will revert the instrumentation when exited.
                Use of this context manager is optional.
        """
    def instrument_asyncpg(self, **kwargs: Unpack[AsyncPGInstrumentKwargs]) -> None:
        """Instrument the `asyncpg` module so that spans are automatically created for each query."""
    def instrument_httpx(self, **kwargs: Unpack[HTTPXInstrumentKwargs]) -> None:
        """Instrument the `httpx` module so that spans are automatically created for each request.

        Uses the
        [OpenTelemetry HTTPX Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html)
        library, specifically `HTTPXClientInstrumentor().instrument()`, to which it passes `**kwargs`.
        """
    def instrument_celery(self, **kwargs: Unpack[CeleryInstrumentKwargs]) -> None:
        """Instrument `celery` so that spans are automatically created for each task.

        Uses the
        [OpenTelemetry Celery Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/celery/celery.html)
        library.
        """
    def instrument_django(self, capture_headers: bool = False, is_sql_commentor_enabled: bool | None = None, request_hook: Callable[[Span, HttpRequest], None] | None = None, response_hook: Callable[[Span, HttpRequest, HttpResponse], None] | None = None, excluded_urls: str | None = None, **kwargs: Any) -> None:
        """Instrument `django` so that spans are automatically created for each web request.

        Uses the
        [OpenTelemetry Django Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html)
        library.

        Args:
            capture_headers: Set to `True` to capture all request and response headers.
            is_sql_commentor_enabled: Adds comments to SQL queries performed by Django,
                so that database logs have additional context.

                This does NOT create spans/logs for the queries themselves.
                For that you need to instrument the database driver, e.g. with `logfire.instrument_psycopg()`.

                To configure the SQL Commentor, see the OpenTelemetry documentation for the
                values that need to be added to `settings.py`.

            request_hook: A function called right after a span is created for a request.
                The function should accept two arguments: the span and the Django `Request` object.

            response_hook: A function called right before a span is finished for the response.
                The function should accept three arguments:
                the span, the Django `Request` object, and the Django `Response` object.

            excluded_urls: A string containing a comma-delimited list of regexes used to exclude URLs from tracking.

            **kwargs: Additional keyword arguments to pass to the OpenTelemetry `instrument` method,
                for future compatibility.

        """
    def instrument_requests(self, excluded_urls: str | None = None, **kwargs: Any) -> None:
        """Instrument the `requests` module so that spans are automatically created for each request.

        Args:
            excluded_urls: A string containing a comma-delimited list of regexes used to exclude URLs from tracking
            **kwargs: Additional keyword arguments to pass to the OpenTelemetry `instrument` methods,
                particularly `request_hook` and `response_hook`.
        """
    def instrument_psycopg(self, conn_or_module: Any = None, **kwargs: Unpack[PsycopgInstrumentKwargs]) -> None:
        """Instrument a `psycopg` connection or module so that spans are automatically created for each query.

        Uses the OpenTelemetry instrumentation libraries for
        [`psycopg`](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg/psycopg.html)
        and
        [`psycopg2`](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg2/psycopg2.html).

        Args:
            conn_or_module: Can be:

                - The `psycopg` (version 3) or `psycopg2` module.
                - The string `'psycopg'` or `'psycopg2'` to instrument the module.
                - `None` (the default) to instrument whichever module(s) are installed.
                - A `psycopg` or `psycopg2` connection.

            **kwargs: Additional keyword arguments to pass to the OpenTelemetry `instrument` methods,
                particularly `enable_commenter` and `commenter_options`.
        """
    def instrument_flask(self, app: Flask, *, capture_headers: bool = False, **kwargs: Unpack[FlaskInstrumentKwargs]) -> None:
        """Instrument `app` so that spans are automatically created for each request.

        Set `capture_headers` to `True` to capture all request and response headers.

        Uses the
        [OpenTelemetry Flask Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/flask/flask.html)
        library, specifically `FlaskInstrumentor().instrument_app()`, to which it passes `**kwargs`.
        """
    def instrument_starlette(self, app: Starlette, *, capture_headers: bool = False, record_send_receive: bool = False, **kwargs: Unpack[StarletteInstrumentKwargs]) -> None:
        """Instrument `app` so that spans are automatically created for each request.

        Set `capture_headers` to `True` to capture all request and response headers.

        Set `record_send_receive` to `True` to allow the OpenTelemetry ASGI to create send/receive spans.
        These are disabled by default to reduce overhead and the number of spans created,
        since many can be created for a single request, and they are not often useful.
        If enabled, they will be set to debug level, meaning they will usually still be hidden in the UI.

        Uses the
        [OpenTelemetry Starlette Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/starlette/starlette.html)
        library, specifically `StarletteInstrumentor.instrument_app()`, to which it passes `**kwargs`.
        """
    def instrument_aiohttp_client(self, **kwargs: Any) -> None:
        """Instrument the `aiohttp` module so that spans are automatically created for each client request.

        Uses the
        [OpenTelemetry aiohttp client Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aiohttp_client/aiohttp_client.html)
        library, specifically `AioHttpClientInstrumentor().instrument()`, to which it passes `**kwargs`.
        """
    def instrument_sqlalchemy(self, **kwargs: Unpack[SQLAlchemyInstrumentKwargs]) -> None:
        """Instrument the `sqlalchemy` module so that spans are automatically created for each query.

        Uses the
        [OpenTelemetry SQLAlchemy Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html)
        library, specifically `SQLAlchemyInstrumentor().instrument()`, to which it passes `**kwargs`.
        """
    def instrument_pymongo(self, **kwargs: Unpack[PymongoInstrumentKwargs]) -> None:
        """Instrument the `pymongo` module so that spans are automatically created for each operation.

        Uses the
        [OpenTelemetry pymongo Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymongo/pymongo.html)
            library, specifically `PymongoInstrumentor().instrument()`, to which it passes `**kwargs`.
        """
    def instrument_redis(self, capture_statement: bool = False, **kwargs: Unpack[RedisInstrumentKwargs]) -> None:
        """Instrument the `redis` module so that spans are automatically created for each operation.

        Uses the
        [OpenTelemetry Redis Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/redis/redis.html)
        library, specifically `RedisInstrumentor().instrument()`, to which it passes `**kwargs`.

        Args:
            capture_statement: Set to `True` to capture the statement in the span attributes.
            kwargs: Additional keyword arguments to pass to the OpenTelemetry `instrument` methods.
        """
    def instrument_mysql(self, conn: MySQLConnection = None, **kwargs: Unpack[MySQLInstrumentKwargs]) -> MySQLConnection:
        """Instrument the `mysql` module or a specific MySQL connection so that spans are automatically created for each operation.

        Uses the
        [OpenTelemetry MySQL Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/mysql/mysql.html)
        library.

        Args:
            conn: The `mysql` connection to instrument, or `None` to instrument all connections.
            **kwargs: Additional keyword arguments to pass to the OpenTelemetry `instrument` methods.

        Returns:
            If a connection is provided, returns the instrumented connection. If no connection is provided, returns None.

        """
    def instrument_system_metrics(self, config: SystemMetricsConfig | None = None, base: SystemMetricsBase = 'basic') -> None:
        """Collect system metrics.

        See [the guide](https://logfire.pydantic.dev/docs/integrations/system-metrics/) for more information.

        Args:
            config: A dictionary where the keys are metric names
                and the values are optional further configuration for that metric.
            base: A string indicating the base config dictionary which `config` will be merged with,
                or `None` for an empty base config.
        """
    def metric_counter(self, name: str, *, unit: str = '', description: str = '') -> Counter:
        """Create a counter metric.

        A counter is a cumulative metric that represents a single numerical value that only ever goes up.

        ```py
        import logfire

        logfire.configure()
        counter = logfire.metric_counter('exceptions', unit='1', description='Number of exceptions caught')

        try:
            raise Exception('oops')
        except Exception:
            counter.add(1)
        ```

        See the [Opentelemetry documentation](https://opentelemetry.io/docs/specs/otel/metrics/api/#counter) about
        counters.

        Args:
            name: The name of the metric.
            unit: The unit of the metric.
            description: The description of the metric.

        Returns:
            The counter metric.
        """
    def metric_histogram(self, name: str, *, unit: str = '', description: str = '') -> Histogram:
        """Create a histogram metric.

        A histogram is a metric that samples observations (usually things like request durations or response sizes).

        ```py
        import logfire

        logfire.configure()
        histogram = logfire.metric_histogram('bank.amount_transferred', unit='$', description='Amount transferred')


        def transfer(amount: int):
            histogram.record(amount)
        ```

        See the [Opentelemetry documentation](https://opentelemetry.io/docs/specs/otel/metrics/api/#histogram) about

        Args:
            name: The name of the metric.
            unit: The unit of the metric.
            description: The description of the metric.

        Returns:
            The histogram metric.
        """
    def metric_gauge(self, name: str, *, unit: str = '', description: str = '') -> Gauge:
        """Create a gauge metric.

        Gauge is a synchronous instrument which can be used to record non-additive measurements.

        ```py
        import logfire

        logfire.configure()
        gauge = logfire.metric_gauge('system.cpu_usage', unit='%', description='CPU usage')


        def update_cpu_usage(cpu_percent):
            gauge.set(cpu_percent)
        ```

        See the [Opentelemetry documentation](https://opentelemetry.io/docs/specs/otel/metrics/api/#gauge) about gauges.

        Args:
            name: The name of the metric.
            unit: The unit of the metric.
            description: The description of the metric.

        Returns:
            The gauge metric.
        """
    def metric_up_down_counter(self, name: str, *, unit: str = '', description: str = '') -> UpDownCounter:
        """Create an up-down counter metric.

        An up-down counter is a cumulative metric that represents a single numerical value that can be adjusted up or
        down.

        ```py
        import logfire

        logfire.configure()
        up_down_counter = logfire.metric_up_down_counter('users.logged_in', unit='1', description='Users logged in')


        def on_login(user):
            up_down_counter.add(1)


        def on_logout(user):
            up_down_counter.add(-1)
        ```

        See the [Opentelemetry documentation](https://opentelemetry.io/docs/specs/otel/metrics/api/#updowncounter) about
        up-down counters.

        Args:
            name: The name of the metric.
            unit: The unit of the metric.
            description: The description of the metric.

        Returns:
            The up-down counter metric.
        """
    def metric_counter_callback(self, name: str, *, callbacks: Sequence[CallbackT], unit: str = '', description: str = '') -> None:
        """Create a counter metric that uses a callback to collect observations.

        The counter metric is a cumulative metric that represents a single numerical value that only ever goes up.

        ```py
        import logfire
        import psutil
        from opentelemetry.metrics import CallbackOptions, Observation

        logfire.configure()


        def cpu_usage_callback(options: CallbackOptions):
            cpu_percents = psutil.cpu_percent(percpu=True)

            for i, cpu_percent in enumerate(cpu_percents):
                yield Observation(cpu_percent, {'cpu': i})


        cpu_usage_counter = logfire.metric_counter_callback(
            'system.cpu.usage',
            callbacks=[cpu_usage_callback],
            unit='%',
            description='CPU usage',
        )
        ```

        See the [Opentelemetry documentation](https://opentelemetry.io/docs/specs/otel/metrics/api/#asynchronous-counter)
        about asynchronous counter.

        Args:
            name: The name of the metric.
            callbacks: A sequence of callbacks that return an iterable of
                [Observation](https://opentelemetry-python.readthedocs.io/en/latest/api/metrics.html#opentelemetry.metrics.Observation).
            unit: The unit of the metric.
            description: The description of the metric.
        """
    def metric_gauge_callback(self, name: str, callbacks: Sequence[CallbackT], *, unit: str = '', description: str = '') -> None:
        """Create a gauge metric that uses a callback to collect observations.

        The gauge metric is a metric that represents a single numerical value that can arbitrarily go up and down.

        ```py
        import threading

        import logfire
        from opentelemetry.metrics import CallbackOptions, Observation

        logfire.configure()


        def thread_count_callback(options: CallbackOptions):
            yield Observation(threading.active_count())


        logfire.metric_gauge_callback(
            'system.thread_count',
            callbacks=[thread_count_callback],
            unit='1',
            description='Number of threads',
        )
        ```

        See the [Opentelemetry documentation](https://opentelemetry.io/docs/specs/otel/metrics/api/#asynchronous-gauge)
        about asynchronous gauge.

        Args:
            name: The name of the metric.
            callbacks: A sequence of callbacks that return an iterable of
                [Observation](https://opentelemetry-python.readthedocs.io/en/latest/api/metrics.html#opentelemetry.metrics.Observation).
            unit: The unit of the metric.
            description: The description of the metric.
        """
    def metric_up_down_counter_callback(self, name: str, callbacks: Sequence[CallbackT], *, unit: str = '', description: str = '') -> None:
        """Create an up-down counter metric that uses a callback to collect observations.

        The up-down counter is a cumulative metric that represents a single numerical value that can be adjusted up or
        down.

        ```py
        import logfire
        from opentelemetry.metrics import CallbackOptions, Observation

        logfire.configure()

        items = []


        def inventory_callback(options: CallbackOptions):
            yield Observation(len(items))


        logfire.metric_up_down_counter_callback(
            name='store.inventory',
            description='Number of items in the inventory',
            callbacks=[inventory_callback],
        )
        ```

        See the [Opentelemetry documentation](https://opentelemetry.io/docs/specs/otel/metrics/api/#asynchronous-updowncounter)
        about asynchronous up-down counters.

        Args:
            name: The name of the metric.
            callbacks: A sequence of callbacks that return an iterable of
                [Observation](https://opentelemetry-python.readthedocs.io/en/latest/api/metrics.html#opentelemetry.metrics.Observation).
            unit: The unit of the metric.
            description: The description of the metric.
        """
    def shutdown(self, timeout_millis: int = 30000, flush: bool = True) -> bool:
        """Shut down all tracers and meters.

        This will clean up any resources used by the tracers and meters and flush any remaining spans and metrics.

        Args:
            timeout_millis: The timeout in milliseconds.
            flush: Whether to flush remaining spans and metrics before shutting down.

        Returns:
            `False` if the timeout was reached before the shutdown was completed, `True` otherwise.
        """

class FastLogfireSpan:
    """A simple version of `LogfireSpan` optimized for auto-tracing."""
    def __init__(self, span: trace_api.Span) -> None: ...
    def __enter__(self) -> FastLogfireSpan: ...
    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: Any) -> None: ...

class LogfireSpan(ReadableSpan):
    end_on_exit: bool
    def __init__(self, span_name: str, otlp_attributes: dict[str, otel_types.AttributeValue], tracer: Tracer, json_schema_properties: JsonSchemaProperties) -> None: ...
    def __getattr__(self, name: str) -> Any: ...
    def __enter__(self) -> LogfireSpan: ...
    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: Any) -> None: ...
    @property
    def message_template(self) -> str | None: ...
    @property
    def tags(self) -> tuple[str, ...]: ...
    @tags.setter
    def tags(self, new_tags: Sequence[str]) -> None: ...
    @property
    def message(self) -> str: ...
    @message.setter
    def message(self, message: str): ...
    def end(self) -> None:
        """Sets the current time as the span's end time.

        The span's end time is the wall time at which the operation finished.

        Only the first call to this method is recorded, further calls are ignored so you
        can call this within the span's context manager to end it before the context manager
        exits.
        """
    def set_attribute(self, key: str, value: Any) -> None:
        """Sets an attribute on the span.

        Args:
            key: The key of the attribute.
            value: The value of the attribute.
        """
    def set_attributes(self, attributes: dict[str, otel_types.AttributeValue]) -> None:
        """Sets the given attributes on the span."""
    def record_exception(self, exception: BaseException, attributes: otel_types.Attributes = None, timestamp: int | None = None, escaped: bool = False) -> None:
        """Records an exception as a span event.

        Delegates to the OpenTelemetry SDK `Span.record_exception` method.
        """
    def is_recording(self) -> bool: ...
    def set_level(self, level: LevelName | int):
        """Set the log level of this span."""

class NoopSpan:
    """Implements the same methods as `LogfireSpan` but does nothing.

    Used in place of `LogfireSpan` and `FastLogfireSpan` when an exception occurs during span creation.
    This way code like:

        with logfire.span(...) as span:
            span.set_attribute(...)

    doesn't raise an error even if `logfire.span` fails internally.
    If `logfire.span` just returned `None` then the `with` block and the `span.set_attribute` call would raise an error.

    TODO this should also be used when tracing is disabled, e.g. before `logfire.configure()` has been called.
    """
    def __init__(self, /, *_args: Any, **__kwargs: Any) -> None: ...
    def __getattr__(self, _name: str) -> Any: ...
    def __enter__(self) -> NoopSpan: ...
    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: Any) -> None: ...
    @property
    def message_template(self) -> str: ...
    @property
    def tags(self) -> tuple[str, ...]: ...
    @tags.setter
    def tags(self, new_tags: Sequence[str]) -> None: ...
    @property
    def message(self) -> str: ...
    @message.setter
    def message(self, message: str): ...
    def is_recording(self) -> bool: ...
AttributesValueType = TypeVar('AttributesValueType', bound=Any | otel_types.AttributeValue)

def user_attributes(attributes: dict[str, Any]) -> dict[str, otel_types.AttributeValue]:
    """Prepare attributes for sending to OpenTelemetry.

    This will convert any non-OpenTelemetry compatible types to JSON.
    """
def set_user_attribute(otlp_attributes: dict[str, otel_types.AttributeValue], key: str, value: Any) -> tuple[str, otel_types.AttributeValue]:
    """Convert a user attribute to an OpenTelemetry compatible type and add it to the given dictionary.

    Returns the final key and value that was added to the dictionary.
    The key will be the original key unless the value was `None`, in which case it will be `NULL_ARGS_KEY`.
    """
P = ParamSpec('P')
R = TypeVar('R')
