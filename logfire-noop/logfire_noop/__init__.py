"""**Logfire** is the observability tool focused on developer experience."""

from __future__ import annotations

import contextlib
import typing
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Callable, ContextManager, Iterable, Literal, Sequence, TypeVar, Union

from fastapi import FastAPI
from git import TYPE_CHECKING

from .version import VERSION

if TYPE_CHECKING:
    import openai
    from fastapi import FastAPI
    from opentelemetry.metrics import (
        CallbackT,
        Counter,
        Histogram,
        NoOpCounter,
        NoOpHistogram,
        NoOpUpDownCounter,
        UpDownCounter,
    )
    from starlette.requests import Request
    from starlette.websockets import WebSocket
    from typing_extensions import LiteralString, ParamSpec, TypeAlias

    _PARAMS = ParamSpec('_PARAMS')
    _RETURN = TypeVar('_RETURN')


LevelName = Literal['trace', 'debug', 'info', 'notice', 'warn', 'warning', 'error', 'fatal']

ExcInfo: TypeAlias = Union[
    'tuple[type[BaseException], BaseException, TracebackType | None]',
    'tuple[None, None, None]',
    BaseException,
    bool,
    None,
]


class Logfire:
    """The main logfire class."""

    def span(
        self,
        msg_template: LiteralString,
        /,
        *,
        _tags: Sequence[str] | None = None,
        _span_name: str | None = None,
        _level: LevelName | None = None,
        _stack_offset: int = 3,
        **attributes: Any,
    ) -> LogfireSpan:
        """Context manager for creating a span.

        ```py
        import logfire

        with logfire.span('This is a span {a=}', a='data'):
            logfire.info('new log 1')
        ```

        Args:
            msg_template: The template for the span message.
            _span_name: The span name. If not provided, the `msg_template` will be used.
            _tags: An optional sequence of tags to include in the span.
            _level: An optional log level name.
            _stack_offset: The stack level offset to use when collecting stack info, defaults to `3`.
            attributes: The arguments to include in the span and format the message template with.
                Attributes starting with an underscore are not allowed.
        """
        return LogfireSpan()

    def instrument(
        self,
        msg_template: typing.LiteralString | None = None,
        *,
        span_name: str | None = None,
        extract_args: bool = True,
    ) -> Callable[[Callable[_PARAMS, _RETURN]], Callable[_PARAMS, _RETURN]]:
        """Decorator for instrumenting a function as a span.

        ```py
        import logfire


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

        def decorator(func: Callable[_PARAMS, _RETURN]) -> Callable[_PARAMS, _RETURN]:
            return func

        return decorator

    def force_flush(self, timeout_millis: int = 3_000) -> bool:
        """Force flush all spans.

        Args:
            timeout_millis: The timeout in milliseconds.

        Returns:
            Whether the flush was successful.
        """
        return True

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
        return contextlib.nullcontext()

    def install_auto_tracing(
        self,
        modules: Sequence[str] | Callable[[AutoTraceModule], bool] | None = None,
        *,
        check_imported_modules: Literal['error', 'warn', 'ignore'] = 'error',
        min_duration: float = 0,
    ) -> None:
        """Install automatic tracing.

        This will trace all function calls in the modules specified by the modules argument.
        It's equivalent to wrapping the body of every function in matching modules in `with logfire.span(...):`.

        !!! note
            This function MUST be called before any of the modules to be traced are imported.

        This works by inserting a new meta path finder into `sys.meta_path`, so inserting another finder before it
        may prevent it from working.

        It relies on being able to retrieve the source code via at least one other existing finder in the meta path,
        so it may not work if standard finders are not present or if the source code is not available.
        A modified version of the source code is then compiled and executed in place of the original module.

        Args:
            modules: List of module names to trace, or a function which returns True for modules that should be traced.
                If a list is provided, any submodules within a given module will also be traced.

                Defaults to the root of the calling module, so e.g. calling this inside the module `foo.bar`
                will trace all functions in `foo`, `foo.bar`, `foo.spam`, etc.
            check_imported_modules: If this is `'error'` (the default), then an exception will be raised if any of the
                modules in `sys.modules` (i.e. modules that have already been imported) match the modules to trace.
                Set to `'warn'` to issue a warning instead, or `'ignore'` to skip the check.
            min_duration: An optional minimum duration in seconds for which a function must run before it's traced.
                The default is `0`, which means all functions are traced from the beginning.
                Otherwise, the first time(s) each function is called, it will be timed but not traced.
                Only after the function has run for at least `min_duration` will it be traced in subsequent calls.
        """

    def instrument_fastapi(
        self,
        app: FastAPI,
        *,
        request_attributes_mapper: Callable[
            [
                Request | WebSocket,
                dict[str, Any],
            ],
            dict[str, Any] | None,
        ]
        | None = None,
        use_opentelemetry_instrumentation: bool = True,
        excluded_urls: str | Iterable[str] | None = None,
    ) -> ContextManager[None]:
        """Instrument a FastAPI app so that spans and logs are automatically created for each request.

        Args:
            app: The FastAPI app to instrument.
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

        Returns:
            A context manager that will revert the instrumentation when exited.
                This context manager doesn't take into account threads or other concurrency.
                Calling this method will immediately apply the instrumentation
                without waiting for the context manager to be opened,
                i.e. it's not necessary to use this as a context manager.
        """
        return contextlib.nullcontext()

    def instrument_openai(
        self,
        openai_client: openai.OpenAI | openai.AsyncOpenAI,
        *,
        suppress_other_instrumentation: bool = True,
    ) -> ContextManager[None]:
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
            openai_client: The OpenAI client to instrument, either `openai.OpenAI` or `openai.AsyncOpenAI`.
            suppress_other_instrumentation: If True, suppress any other OTEL instrumentation that may be otherwise
                enabled. In reality, this means the HTTPX instrumentation, which could otherwise be called since
                OpenAI uses HTTPX to make HTTP requests.

        Returns:
            A context manager that will revert the instrumentation when exited.
                Use of this context manager is optional.
        """
        return contextlib.nullcontext()

    def instrument_asyncpg(self):
        """Instrument the `asyncpg` module so that spans are automatically created for each query."""

    def instrument_psycopg(self, conn_or_module: Any = None, **kwargs: Any) -> None:
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

    def shutdown(self, timeout_millis: int = 30_000, flush: bool = True) -> bool:  # pragma: no cover
        """Shut down all tracers and meters.

        This will clean up any resources used by the tracers and meters and flush any remaining spans and metrics.

        Args:
            timeout_millis: The timeout in milliseconds.
            flush: Whether to flush remaining spans and metrics before shutting down.

        Returns:
            `False` if the timeout was reached before the shutdown was completed, `True` otherwise.
        """
        return True

    def with_tags(self, *tags: str) -> Logfire:
        """A new Logfire instance which always uses the given tags.

        ```py
        import logfire

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
        return self

    def with_settings(
        self,
        *,
        tags: Sequence[str] = (),
        stack_offset: int | None = None,
        console_log: bool | None = None,
        custom_scope_suffix: str | None = None,
    ) -> Logfire:
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
        return self

    def log(
        self,
        level: LevelName,
        msg_template: LiteralString,
        attributes: dict[str, Any] | None = None,
        tags: Sequence[str] | None = None,
        exc_info: ExcInfo = False,
        stack_offset: int | None = None,
        console_log: bool | None = None,
        custom_scope_suffix: str | None = None,
    ) -> None:
        """Log a message.

        ```py
        import logfire

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
            stack_offset: The stack level offset to use when collecting stack info, also affects the warning which
                message formatting might emit, defaults to `0` which means the stack info will be collected from the
                position where [`logfire.log`][logfire.Logfire.log] was called.
            console_log: Whether to log to the console, defaults to `True`.
            custom_scope_suffix: A custom suffix to append to `logfire.` e.g. `logfire.loguru`.

                It should only be used when instrumenting another library with Logfire, such as structlog or loguru.

                See the `instrumenting_module_name` parameter on
                [TracerProvider.get_tracer][opentelemetry.sdk.trace.TracerProvider.get_tracer] for more info.
        """

    def trace(
        self,
        msg_template: LiteralString,
        /,
        *,
        _tags: Sequence[str] | None = None,
        _exc_info: ExcInfo = False,
        **attributes: Any,
    ) -> None:
        """Log a trace message.

        ```py
        import logfire

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

    def debug(
        self,
        msg_template: LiteralString,
        /,
        *,
        _tags: Sequence[str] | None = None,
        _exc_info: ExcInfo = False,
        **attributes: Any,
    ) -> None:
        """Log a debug message.

        ```py
        import logfire

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

    def info(
        self,
        msg_template: LiteralString,
        /,
        *,
        _tags: Sequence[str] | None = None,
        _exc_info: ExcInfo = False,
        **attributes: Any,
    ) -> None:
        """Log an info message.

        ```py
        import logfire

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

    def notice(
        self,
        msg_template: LiteralString,
        /,
        *,
        _tags: Sequence[str] | None = None,
        _exc_info: ExcInfo = False,
        **attributes: Any,
    ) -> None:
        """Log a notice message.

        ```py
        import logfire

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

    def warn(
        self,
        msg_template: LiteralString,
        /,
        *,
        _tags: Sequence[str] | None = None,
        _exc_info: ExcInfo = False,
        **attributes: Any,
    ) -> None:
        """Log a warning message.

        ```py
        import logfire

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

    def error(
        self,
        msg_template: LiteralString,
        /,
        *,
        _tags: Sequence[str] | None = None,
        _exc_info: ExcInfo = False,
        **attributes: Any,
    ) -> None:
        """Log an error message.

        ```py
        import logfire

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

    def fatal(
        self,
        msg_template: LiteralString,
        /,
        *,
        _tags: Sequence[str] | None = None,
        _exc_info: ExcInfo = False,
        **attributes: Any,
    ) -> None:
        """Log a fatal message.

        ```py
        import logfire

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

    def exception(
        self,
        msg_template: LiteralString,
        /,
        *,
        _tags: Sequence[str] | None = None,
        _exc_info: ExcInfo = True,
        **attributes: Any,
    ) -> None:
        """The same as `error` but with `_exc_info=True` by default.

        This means that a traceback will be logged for any currently handled exception.

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.
            _tags: An optional sequence of tags to include in the log.
            _exc_info: Set to an exception or a tuple as returned by [`sys.exc_info()`][sys.exc_info]
                to record a traceback with the log message.
        """

    def metric_counter(self, name: str, *, unit: str = '', description: str = '') -> Counter:
        """Create a counter metric.

        A counter is a cumulative metric that represents a single numerical value that only ever goes up.

        ```py
        import logfire

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
        return NoOpCounter(name=name, unit=unit, description=description)

    def metric_histogram(self, name: str, *, unit: str = '', description: str = '') -> Histogram:
        """Create a histogram metric.

        A histogram is a metric that samples observations (usually things like request durations or response sizes).

        ```py
        import logfire

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
        return NoOpHistogram(name, unit, description)

    def metric_up_down_counter(self, name: str, *, unit: str = '', description: str = '') -> UpDownCounter:
        """Create an up-down counter metric.

        An up-down counter is a cumulative metric that represents a single numerical value that can be adjusted up or
        down.

        ```py
        import logfire

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
        return NoOpUpDownCounter(name, unit, description)

    def metric_counter_callback(
        self,
        name: str,
        *,
        callbacks: Sequence[CallbackT],
        unit: str = '',
        description: str = '',
    ) -> None:
        """Create a counter metric that uses a callback to collect observations.

        The counter metric is a cumulative metric that represents a single numerical value that only ever goes up.

        ```py
        import logfire
        import psutil
        from opentelemetry.metrics import CallbackOptions, Observation


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

    def metric_gauge_callback(
        self, name: str, callbacks: Sequence[CallbackT], *, unit: str = '', description: str = ''
    ) -> None:
        """Create a gauge metric that uses a callback to collect observations.

        The gauge metric is a metric that represents a single numerical value that can arbitrarily go up and down.

        ```py
        import threading

        import logfire
        from opentelemetry.metrics import CallbackOptions, Observation


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

    def metric_up_down_counter_callback(
        self, name: str, callbacks: Sequence[CallbackT], *, unit: str = '', description: str = ''
    ) -> None:
        """Create an up-down counter metric that uses a callback to collect observations.

        The up-down counter is a cumulative metric that represents a single numerical value that can be adjusted up or
        down.

        ```py
        import logfire
        from opentelemetry.metrics import CallbackOptions, Observation

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


class LogfireSpan: ...


DEFAULT_LOGFIRE_INSTANCE = Logfire()
span = DEFAULT_LOGFIRE_INSTANCE.span
instrument = DEFAULT_LOGFIRE_INSTANCE.instrument
force_flush = DEFAULT_LOGFIRE_INSTANCE.force_flush
log_slow_async_callbacks = DEFAULT_LOGFIRE_INSTANCE.log_slow_async_callbacks
install_auto_tracing = DEFAULT_LOGFIRE_INSTANCE.install_auto_tracing
instrument_fastapi = DEFAULT_LOGFIRE_INSTANCE.instrument_fastapi
instrument_openai = DEFAULT_LOGFIRE_INSTANCE.instrument_openai
instrument_asyncpg = DEFAULT_LOGFIRE_INSTANCE.instrument_asyncpg
instrument_psycopg = DEFAULT_LOGFIRE_INSTANCE.instrument_psycopg
shutdown = DEFAULT_LOGFIRE_INSTANCE.shutdown
with_tags = DEFAULT_LOGFIRE_INSTANCE.with_tags
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
metric_counter_callback = DEFAULT_LOGFIRE_INSTANCE.metric_counter_callback
metric_gauge_callback = DEFAULT_LOGFIRE_INSTANCE.metric_gauge_callback
metric_up_down_counter_callback = DEFAULT_LOGFIRE_INSTANCE.metric_up_down_counter_callback


def loguru_handler() -> dict[str, Any]:
    """Create a **Logfire** handler for Loguru.

    Returns:
        A dictionary with the handler and format for Loguru.
    """
    return {}


__version__ = VERSION

__all__ = (
    'Logfire',
    'LogfireSpan',
    'LevelName',
    # 'ConsoleOptions',
    # 'PydanticPlugin',
    # 'configure',
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
    # 'load_spans_from_file',
    # 'no_auto_trace',
    # 'METRICS_PREFERRED_TEMPORALITY',
    # 'ScrubMatch',
    'VERSION',
)


@dataclass
class AutoTraceModule:
    """Information about a module being imported that should maybe be traced automatically.

    This object will be passed to a function that should return True if the module should be traced.
    In particular it'll be passed to a function that's passed to `install_auto_tracing` as the `modules` argument.
    """

    name: str
    """Fully qualified absolute name of the module being imported."""

    filename: str | None
    """Filename of the module being imported."""

    # The argument is meant to match `str.startswith`.
    # The method name is different to avoid confusion with `.name.startswith` which behaves slightly differently.
    def parts_start_with(self, prefix: str | Sequence[str]) -> bool:
        """Return True if the module name starts with any of the given prefixes, using dots as boundaries.

        For example, if the module name is `foo.bar.spam`, then `parts_start_with('foo')` will return True,
        but `parts_start_with('bar')` or `parts_start_with('foo_bar')` will return False.
        In other words, this will match the module itself or any submodules.

        If a prefix contains any characters other than letters, numbers, and dots,
        then it will be treated as a regular expression.
        """
        return True
