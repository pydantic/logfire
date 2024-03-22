from __future__ import annotations

import sys
import traceback
import typing
import warnings
from functools import cached_property
from time import time
from types import TracebackType
from typing import TYPE_CHECKING, Any, Callable, ContextManager, Iterable, Literal, Sequence, TypeVar, Union, cast

import opentelemetry.context as context_api
import opentelemetry.trace as trace_api
from opentelemetry.metrics import CallbackT, Counter, Histogram, UpDownCounter
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer
from opentelemetry.util import types as otel_types
from typing_extensions import LiteralString, ParamSpec

from logfire._config import GLOBAL_CONFIG, LogfireConfig
from logfire._formatter import logfire_format
from logfire._instrument import LogfireArgs, instrument
from logfire.version import VERSION

from . import AutoTraceModule, _async
from ._auto_trace import install_auto_tracing
from ._constants import (
    ATTRIBUTES_JSON_SCHEMA_KEY,
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_SAMPLE_RATE_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    ATTRIBUTES_TAGS_KEY,
    ATTRIBUTES_VALIDATION_ERROR_KEY,
    DISABLE_CONSOLE_KEY,
    NULL_ARGS_KEY,
    OTLP_MAX_INT_SIZE,
    LevelName,
    log_level_attributes,
)
from ._json_encoder import logfire_json_dumps
from ._json_schema import (
    JsonSchemaProperties,
    attributes_json_schema,
    attributes_json_schema_properties,
    create_json_schema,
)
from ._metrics import ProxyMeterProvider
from ._stack_info import get_caller_stack_info
from ._tracer import ProxyTracerProvider
from ._utils import uniquify_sequence

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.requests import Request
    from starlette.websockets import WebSocket

try:
    from pydantic import ValidationError
except ImportError:  # pragma: no cover
    ValidationError = None


# This is the type of the exc_info/_exc_info parameter of the log methods.
# sys.exc_info() returns a tuple of (type, value, traceback) or (None, None, None).
# We just need the exception, but we allow the user to pass the tuple because:
# 1. It's convenient to pass the result of sys.exc_info() directly
# 2. It mirrors the exc_info argument of the stdlib logging methods
# 3. The argument name exc_info is very suggestive of the sys function.
ExcInfo: typing.TypeAlias = (
    'tuple[type[BaseException], BaseException, TracebackType] | tuple[None, None, None] | BaseException | bool | None'
)


class Logfire:
    """The main logfire class."""

    def __init__(
        self,
        tags: Sequence[str] = (),
        config: LogfireConfig = GLOBAL_CONFIG,
        sample_rate: float | None = None,
    ) -> None:
        self._tags = list(tags)
        self._config = config
        self._sample_rate = sample_rate

    @property
    def config(self) -> LogfireConfig:
        return self._config

    def with_trace_sample_rate(self, sample_rate: float) -> Logfire:  # pragma: no cover
        """A new Logfire instance with the given sampling ratio applied.

        Args:
            sample_rate: The sampling ratio to use.

        Returns:
            A new Logfire instance with the sampling ratio applied.
        """
        if sample_rate > 1 or sample_rate < 0:
            raise ValueError('sample_rate must be between 0 and 1')
        return Logfire(self._tags, self._config, sample_rate)

    @cached_property
    def _tracer_provider(self) -> ProxyTracerProvider:
        return self._config.get_tracer_provider()

    @cached_property
    def _meter_provider(self) -> ProxyMeterProvider:
        return self._config.get_meter_provider()

    @cached_property
    def _logs_tracer(self) -> Tracer:
        return self._get_tracer(is_span_tracer=False)

    @cached_property
    def _spans_tracer(self) -> Tracer:
        return self._get_tracer(is_span_tracer=True)

    def _get_tracer(self, *, is_span_tracer: bool, otel_scope: str = 'logfire') -> Tracer:
        return self._tracer_provider.get_tracer(
            otel_scope,
            VERSION,
            is_span_tracer=is_span_tracer,
        )

    # If any changes are made to this method, they may need to be reflected in `_fast_span` as well.
    def _span(
        self,
        msg_template: LiteralString,
        attributes: dict[str, Any],
        *,
        _tags: Sequence[str] | None = None,
        _span_name: str | None = None,
        _level: LevelName | None = None,
        stacklevel: int = 3,
    ) -> LogfireSpan:
        stack_info = get_caller_stack_info(stacklevel=stacklevel)
        merged_attributes = {**stack_info, **attributes}

        log_message = logfire_format(msg_template, merged_attributes, self._config.scrubber, stacklevel=stacklevel + 2)
        merged_attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] = msg_template
        merged_attributes[ATTRIBUTES_MESSAGE_KEY] = log_message

        otlp_attributes = user_attributes(merged_attributes)

        if json_schema_properties := attributes_json_schema_properties(attributes):
            otlp_attributes[ATTRIBUTES_JSON_SCHEMA_KEY] = attributes_json_schema(json_schema_properties)

        tags = (self._tags or []) + list(_tags or [])
        if tags:
            otlp_attributes[ATTRIBUTES_TAGS_KEY] = uniquify_sequence(tags)

        sample_rate = (
            self._sample_rate
            if self._sample_rate is not None
            else otlp_attributes.pop(ATTRIBUTES_SAMPLE_RATE_KEY, None)
        )
        if sample_rate is not None and sample_rate != 1:  # pragma: no cover
            otlp_attributes[ATTRIBUTES_SAMPLE_RATE_KEY] = sample_rate

        if _level is not None:
            otlp_attributes.update(log_level_attributes(_level))

        return LogfireSpan(
            _span_name or msg_template,
            otlp_attributes,
            self._spans_tracer,
            json_schema_properties,
        )

    def _fast_span(self, name: str, attributes: otel_types.Attributes) -> FastLogfireSpan:
        """A simple version of `_span` optimized for auto-tracing that doesn't support message formatting.

        Returns a similarly simplified version of `LogfireSpan` which must immediately be used as a context manager.
        """
        span = self._spans_tracer.start_span(name=name, attributes=attributes)
        return FastLogfireSpan(span)

    def _instrument_span_with_args(
        self, name: str, attributes: dict[str, otel_types.AttributeValue], function_args: dict[str, Any]
    ) -> FastLogfireSpan:
        """A version of `_span` used by `@instrument` with `extract_args=True`.

        This is a bit faster than `_span` but not as fast as `_fast_span` because it supports message formatting
        and arbitrary types of attributes.
        """
        msg_template: str = attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY]  # type: ignore
        attributes[ATTRIBUTES_MESSAGE_KEY] = logfire_format(
            msg_template, function_args, self._config.scrubber, stacklevel=4
        )
        if json_schema_properties := attributes_json_schema_properties(function_args):
            attributes[ATTRIBUTES_JSON_SCHEMA_KEY] = attributes_json_schema(json_schema_properties)
        attributes.update(user_attributes(function_args))
        return self._fast_span(name, attributes)

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
            _exc_info: Set to an exception or a tuple as returned by `sys.exc_info()`
                to record a traceback with the log message.
                Set to True to use the currently handled exception.
        """
        if any(k.startswith('_') for k in attributes):
            raise ValueError('Attribute keys cannot start with an underscore.')
        self.log('trace', msg_template, attributes, stack_offset=1, tags=_tags, exc_info=_exc_info)

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
            _exc_info: Set to an exception or a tuple as returned by `sys.exc_info()`
                to record a traceback with the log message.
                Set to True to use the currently handled exception.
        """
        if any(k.startswith('_') for k in attributes):
            raise ValueError('Attribute keys cannot start with an underscore.')
        self.log('debug', msg_template, attributes, stack_offset=1, tags=_tags, exc_info=_exc_info)

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
            _exc_info: Set to an exception or a tuple as returned by `sys.exc_info()`
                to record a traceback with the log message.
                Set to True to use the currently handled exception.
        """
        if any(k.startswith('_') for k in attributes):
            raise ValueError('Attribute keys cannot start with an underscore.')
        self.log('info', msg_template, attributes, stack_offset=1, tags=_tags, exc_info=_exc_info)

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
            _exc_info: Set to an exception or a tuple as returned by `sys.exc_info()`
                to record a traceback with the log message.
                Set to True to use the currently handled exception.
        """
        if any(k.startswith('_') for k in attributes):
            raise ValueError('Attribute keys cannot start with an underscore.')
        self.log('notice', msg_template, attributes, stack_offset=1, tags=_tags, exc_info=_exc_info)

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
            _exc_info: Set to an exception or a tuple as returned by `sys.exc_info()`
                to record a traceback with the log message.
                Set to True to use the currently handled exception.
        """
        if any(k.startswith('_') for k in attributes):
            raise ValueError('Attribute keys cannot start with an underscore.')
        self.log('warn', msg_template, attributes, stack_offset=1, tags=_tags, exc_info=_exc_info)

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
            _exc_info: Set to an exception or a tuple as returned by `sys.exc_info()`
                to record a traceback with the log message.
                Set to True to use the currently handled exception.
        """
        if any(k.startswith('_') for k in attributes):
            raise ValueError('Attribute keys cannot start with an underscore.')
        self.log('error', msg_template, attributes, stack_offset=1, tags=_tags, exc_info=_exc_info)

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
            _exc_info: Set to an exception or a tuple as returned by `sys.exc_info()`
                to record a traceback with the log message.
                Set to True to use the currently handled exception.
        """
        if any(k.startswith('_') for k in attributes):
            raise ValueError('Attribute keys cannot start with an underscore.')
        self.log('fatal', msg_template, attributes, stack_offset=1, tags=_tags, exc_info=_exc_info)

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
            _exc_info: Set to an exception or a tuple as returned by `sys.exc_info()`
                to record a traceback with the log message.
        """
        if any(k.startswith('_') for k in attributes):  # pragma: no cover
            raise ValueError('Attribute keys cannot start with an underscore.')
        self.log('error', msg_template, attributes, stack_offset=1, tags=_tags, exc_info=_exc_info)

    def span(
        self,
        msg_template: LiteralString,
        /,
        *,
        _tags: Sequence[str] | None = None,
        _span_name: str | None = None,
        _level: LevelName | None = None,
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

            attributes: The arguments to include in the span and format the message template with.
                Attributes starting with an underscore are not allowed.
        """
        if any(k.startswith('_') for k in attributes):
            raise ValueError('Attribute keys cannot start with an underscore.')
        return self._span(
            msg_template,
            attributes,
            _tags=_tags,
            _span_name=_span_name,
            _level=_level,
        )

    def instrument(
        self,
        msg_template: LiteralString | None = None,
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
        args = LogfireArgs(tuple(self._tags), self._sample_rate, msg_template, span_name, extract_args)
        return instrument(self, args)

    def log(
        self,
        level: LevelName,
        msg_template: LiteralString,
        attributes: dict[str, Any] | None = None,
        tags: Sequence[str] | None = None,
        exc_info: ExcInfo = False,
        stack_offset: int = 0,
        console_log: bool = True,
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
            exc_info: Set to an exception or a tuple as returned by `sys.exc_info()`
                to record a traceback with the log message.
                Set to True to use the currently handled exception.
            stack_offset: The stack level offset to use when collecting stack info, also affects the warning which
                message formatting might emit, defaults to `0` which means the stack info will be collected from the
                position where `logfire.log` was called.
            console_log: Whether to log to the console, defaults to `True`.
            custom_scope_suffix: A custom suffix to append to `logfire.`, should only be used when you're using
                logfire to instrument another library like structlog or loguru.
                See `TraceProvider.get_tracer(instrumenting_module_name)` docstring for more info.
        """
        stacklevel = stack_offset + 2
        stack_info = get_caller_stack_info(stacklevel)

        attributes = attributes or {}
        merged_attributes = {**stack_info, **attributes}
        if (msg := attributes.pop(ATTRIBUTES_MESSAGE_KEY, None)) is None:
            msg = logfire_format(msg_template, merged_attributes, self._config.scrubber, stacklevel=stacklevel + 2)
        otlp_attributes = user_attributes(merged_attributes)
        otlp_attributes = {
            ATTRIBUTES_SPAN_TYPE_KEY: 'log',
            **log_level_attributes(level),
            ATTRIBUTES_MESSAGE_TEMPLATE_KEY: msg_template,
            ATTRIBUTES_MESSAGE_KEY: msg,
            **otlp_attributes,
        }
        if json_schema_properties := attributes_json_schema_properties(attributes):
            otlp_attributes[ATTRIBUTES_JSON_SCHEMA_KEY] = attributes_json_schema(json_schema_properties)

        tags = (self._tags or []) + list(tags or [])
        if tags:
            otlp_attributes[ATTRIBUTES_TAGS_KEY] = uniquify_sequence(tags)

        sample_rate = (
            self._sample_rate
            if self._sample_rate is not None
            else otlp_attributes.pop(ATTRIBUTES_SAMPLE_RATE_KEY, None)
        )
        if sample_rate is not None and sample_rate != 1:  # pragma: no cover
            otlp_attributes[ATTRIBUTES_SAMPLE_RATE_KEY] = sample_rate

        if not console_log:
            otlp_attributes[DISABLE_CONSOLE_KEY] = True
        start_time = self._config.ns_timestamp_generator()

        if custom_scope_suffix:
            tracer = self._get_tracer(is_span_tracer=False, otel_scope=f'logfire.{custom_scope_suffix}')
        else:
            tracer = self._logs_tracer

        span = tracer.start_span(
            msg_template,
            attributes=otlp_attributes,
            start_time=start_time,
        )

        if exc_info:
            if exc_info is True:
                exc_info = sys.exc_info()
            if isinstance(exc_info, tuple):
                exc_info = exc_info[1]
            if isinstance(exc_info, BaseException):
                _record_exception(span, exc_info)
            elif exc_info is not None:  # pragma: no branch
                raise TypeError(f'Invalid type for exc_info: {exc_info.__class__.__name__}')

        span.end(start_time)

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
        return Logfire(self._tags + list(tags), self._config, self._sample_rate)

    def force_flush(self, timeout_millis: int = 3_000) -> bool:
        """Force flush all spans.

        Args:
            timeout_millis: The timeout in milliseconds.

        Returns:
            Whether the flush was successful.
        """
        return self._tracer_provider.force_flush(timeout_millis)

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
        return _async.log_slow_callbacks(self, slow_duration)

    def install_auto_tracing(
        self,
        modules: Sequence[str] | Callable[[AutoTraceModule], bool] | None = None,
        *,
        check_imported_modules: Literal['error', 'warn', 'ignore'] = 'error',
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
        """
        install_auto_tracing(self, modules, check_imported_modules=check_imported_modules)

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
        from .integrations._fastapi import instrument_fastapi

        return instrument_fastapi(
            self,
            app,
            request_attributes_mapper=request_attributes_mapper,
            excluded_urls=excluded_urls,
            use_opentelemetry_instrumentation=use_opentelemetry_instrumentation,
        )

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
        return self._config.meter.create_counter(name, unit, description)

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
        return self._config.meter.create_histogram(name, unit, description)

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
        return self._config.meter.create_up_down_counter(name, unit, description)

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
        self._config.meter.create_observable_counter(name, callbacks, unit, description)

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
        self._config.meter.create_observable_gauge(name, callbacks, unit, description)

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
        self._config.meter.create_observable_up_down_counter(name, callbacks, unit, description)

    def shutdown(self, timeout_millis: int = 30_000, flush: bool = True) -> bool:
        """Shut down all tracers and meters.

        This will clean up any resources used by the tracers and meters and flush any remaining spans and metrics.

        Args:
            timeout_millis: The timeout in milliseconds.
            flush: Whether to flush remaining spans and metrics before shutting down.

        Returns:
            False if the timeout was reached before the shutdown was completed, True otherwise.
        """
        start = time()
        if flush:  # pragma: no branch
            self._tracer_provider.force_flush(timeout_millis)
        remaining = max(0, timeout_millis - (time() - start))
        if not remaining:  # pragma: no cover
            return False
        self._tracer_provider.shutdown()

        remaining = max(0, timeout_millis - (time() - start))
        if not remaining:  # pragma: no cover
            return False
        if flush:  # pragma: no branch
            self._meter_provider.force_flush(remaining)
        remaining = max(0, timeout_millis - (time() - start))
        if not remaining:  # pragma: no cover
            return False
        self._meter_provider.shutdown(remaining)
        return (start - time()) < timeout_millis


class FastLogfireSpan:
    """A simple version of `LogfireSpan` optimized for auto-tracing."""

    __slots__ = ('_span', '_token')

    def __init__(self, span: trace_api.Span) -> None:
        self._span = span
        self._token = context_api.attach(trace_api.set_span_in_context(self._span))

    def __enter__(self) -> FastLogfireSpan:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: Any) -> None:
        context_api.detach(self._token)
        _exit_span(self._span, exc_value)
        self._span.end()


# Changes to this class may need to be reflected in `FastLogfireSpan` as well.
class LogfireSpan(ReadableSpan):
    def __init__(
        self,
        span_name: str,
        otlp_attributes: dict[str, otel_types.AttributeValue],
        tracer: Tracer,
        json_schema_properties: JsonSchemaProperties,
    ) -> None:
        self._span_name = span_name
        self._otlp_attributes = otlp_attributes
        self._tracer = tracer
        self._json_schema_properties = json_schema_properties

        self._added_attributes = False
        self._end_on_exit: bool | None = None
        self._token: None | object = None
        self._span: None | trace_api.Span = None
        self.end_on_exit = True

    if not TYPE_CHECKING:  # pragma: no branch

        def __getattr__(self, name: str) -> Any:
            return getattr(self._span, name)

    def __enter__(self) -> LogfireSpan:
        self.end_on_exit = True
        if self._span is None:
            self._span = self._tracer.start_span(
                name=self._span_name,
                attributes=self._otlp_attributes,
            )
        if self._token is None:  # pragma: no branch
            self._token = context_api.attach(trace_api.set_span_in_context(self._span))
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: Any) -> None:
        if self._token is None:  # pragma: no cover
            return

        context_api.detach(self._token)
        self._token = None

        assert self._span is not None
        _exit_span(self._span, exc_value)

        end_on_exit_ = self.end_on_exit
        if end_on_exit_:
            self.end()

        self._token = None

    @property
    def message_template(self) -> str | None:  # pragma: no cover
        return self._get_attribute(ATTRIBUTES_MESSAGE_TEMPLATE_KEY, None)

    @property
    def tags(self) -> Sequence[str]:  # pragma: no cover
        return self._get_attribute(ATTRIBUTES_TAGS_KEY, [])

    @property
    def message(self) -> str:
        return self._get_attribute(ATTRIBUTES_MESSAGE_KEY, self._span_name)

    @message.setter
    def message(self, message: str):
        if self._span is None:  # pragma: no cover
            self._otlp_attributes[ATTRIBUTES_MESSAGE_KEY] = message
        else:
            self._span.set_attribute(ATTRIBUTES_MESSAGE_KEY, message)

    def end(self) -> None:
        """Sets the current time as the span's end time.

        The span's end time is the wall time at which the operation finished.

        Only the first call to this method is recorded, further calls are ignored so you
        can call this within the span's context manager to end it before the context manager
        exits.
        """
        if self._span is None:  # pragma: no cover
            raise RuntimeError('Span has not been started')
        if self._span.is_recording():
            if self._added_attributes:
                self._span.set_attribute(
                    ATTRIBUTES_JSON_SCHEMA_KEY, attributes_json_schema(self._json_schema_properties)
                )

            self._span.end()

    def set_attribute(self, key: str, value: Any) -> None:
        """Sets an attribute on the span.

        Args:
            key: The key of the attribute.
            value: The value of the attribute.
        """
        self._added_attributes = True
        self._json_schema_properties[key] = create_json_schema(value)
        key, otel_value = set_user_attribute(self._otlp_attributes, key, value)
        if self._span is not None:  # pragma: no branch
            self._span.set_attribute(key, otel_value)

    def set_attributes(self, attributes: dict[str, otel_types.AttributeValue]) -> None:
        """Sets the given attributes on the span."""
        for key, value in attributes.items():
            self.set_attribute(key, value)

    # TODO(Marcelo): We should add a test for `record_exception`.
    def record_exception(
        self,
        exception: BaseException,
        attributes: otel_types.Attributes = None,
        timestamp: int | None = None,
        escaped: bool = False,
    ) -> None:  # pragma: no cover
        """Records an exception as a span event.

        Delegates to the OpenTelemetry SDK `Span.record_exception` method.
        """
        if self._span is None:
            raise RuntimeError('Span has not been started')

        # Check if the span has been sampled out first, since _record_exception is somewhat expensive.
        if not self._span.is_recording():
            return

        _record_exception(
            self._span,
            exception,
            attributes=attributes,
            timestamp=timestamp,
            escaped=escaped,
        )

    def is_recording(self) -> bool:
        return self._span is not None and self._span.is_recording()

    def set_level(self, level_name: LevelName):
        """Set the log level of this span."""
        attributes = log_level_attributes(level_name)
        if self._span is None:
            self._otlp_attributes.update(attributes)
        else:
            self._span.set_attributes(attributes)

    def _get_attribute(self, key: str, default: Any) -> Any:
        attributes = getattr(self._span, 'attributes', self._otlp_attributes)
        return attributes.get(key, default)


def _exit_span(span: trace_api.Span, exception: BaseException | None) -> None:
    if not span.is_recording():
        return

    # record exception if present
    # isinstance is to ignore BaseException
    if isinstance(exception, Exception):
        _record_exception(span, exception, escaped=True)


def _record_exception(
    span: trace_api.Span,
    exception: BaseException,
    *,
    attributes: otel_types.Attributes = None,
    timestamp: int | None = None,
    escaped: bool = False,
) -> None:
    """Similar to the OTEL SDK Span.record_exception method, with our own additions."""
    # From https://opentelemetry.io/docs/specs/semconv/attributes-registry/exception/
    # `escaped=True` means that the exception is escaping the scope of the span.
    # This means we know that the exception hasn't been handled,
    # so we can set the OTEL status and the log level to error.
    if escaped:
        span.set_status(
            trace_api.Status(
                status_code=trace_api.StatusCode.ERROR,
                description=f'{exception.__class__.__name__}: {exception}',
            )
        )
        span.set_attributes(log_level_attributes('error'))

    attributes = {**(attributes or {})}
    if ValidationError is not None and isinstance(exception, ValidationError):
        # insert a more detailed breakdown of pydantic errors
        err_json = exception.json(include_url=False)
        span.set_attribute(ATTRIBUTES_VALIDATION_ERROR_KEY, err_json)
        attributes[ATTRIBUTES_VALIDATION_ERROR_KEY] = err_json

    if exception is not sys.exc_info()[1]:
        # OTEL's record_exception uses `traceback.format_exc()` which is for the current exception,
        # ignoring the passed exception.
        # So we override the stacktrace attribute with the correct one.
        stacktrace = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        attributes[SpanAttributes.EXCEPTION_STACKTRACE] = stacktrace

    span.record_exception(cast(Exception, exception), attributes=attributes, timestamp=timestamp, escaped=escaped)


AttributesValueType = TypeVar('AttributesValueType', bound=Union[Any, otel_types.AttributeValue])


def user_attributes(attributes: dict[str, Any]) -> dict[str, otel_types.AttributeValue]:
    """Prepare attributes for sending to OpenTelemetry.

    This will convert any non-OpenTelemetry compatible types to JSON.
    """
    otlp_attributes: dict[str, otel_types.AttributeValue] = {}

    for key, value in attributes.items():
        set_user_attribute(otlp_attributes, key, value)

    return otlp_attributes


def set_user_attribute(
    otlp_attributes: dict[str, otel_types.AttributeValue], key: str, value: Any
) -> tuple[str, otel_types.AttributeValue]:
    """Convert a user attribute to an OpenTelemetry compatible type and add it to the given dictionary.

    Returns the final key and value that was added to the dictionary.
    The key will be the original key unless the value was `None`, in which case it will be `NULL_ARGS_KEY`.
    """
    otel_value: otel_types.AttributeValue
    if value is None:
        otel_value = cast('list[str]', otlp_attributes.get(NULL_ARGS_KEY, [])) + [key]
        key = NULL_ARGS_KEY
    elif isinstance(value, int):
        if value > OTLP_MAX_INT_SIZE:
            warnings.warn(
                f'Integer value {value} is larger than the maximum OTLP integer size of {OTLP_MAX_INT_SIZE} (64-bits), '
                ' if you need support for sending larger integers, please open a feature request',
                UserWarning,
            )
            otel_value = str(value)
        else:
            otel_value = value
    elif isinstance(value, (str, bool, float)):
        otel_value = value
    else:
        otel_value = logfire_json_dumps(value)
    otlp_attributes[key] = otel_value
    return key, otel_value


_PARAMS = ParamSpec('_PARAMS')
_RETURN = TypeVar('_RETURN')
