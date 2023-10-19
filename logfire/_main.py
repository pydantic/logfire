from __future__ import annotations

import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import Parameter as SignatureParameter, signature as inspect_signature
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ContextManager,
    Iterator,
    LiteralString,
    Mapping,
    Sequence,
    TypeVar,
    cast,
)

import opentelemetry.trace as trace_api
import rich.traceback
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import Tracer
from opentelemetry.util import types as otel_types

from logfire._config import GLOBAL_CONFIG, LogfireConfig

try:
    from pydantic import ValidationError
except ImportError:
    ValidationError = None
from typing_extensions import ParamSpec

from logfire._formatter import logfire_format

from ._constants import (
    ATTRIBUTES_LOG_LEVEL_KEY,
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    ATTRIBUTES_TAGS_KEY,
    ATTRIBUTES_VALIDATION_ERROR_KEY,
    NON_SCALAR_VAR_SUFFIX,
    NULL_ARGS_KEY,
    LevelName,
)
from ._flatten import Flatten
from ._json_encoder import json_dumps_traceback, logfire_json_dumps
from ._tracer import ProxyTracerProvider

_CDW = Path('.').resolve()


class Logfire:
    def __init__(self, tags: Sequence[str] = (), config: LogfireConfig = GLOBAL_CONFIG) -> None:
        self._tags = list(tags)
        self._config = config
        self.__tracer_provider: ProxyTracerProvider | None = None
        self._logs_tracer: Tracer | None = None
        self._spans_tracer: Tracer | None = None

    def tags(self, *tags: str) -> Logfire:
        return Logfire(self._tags + list(tags), self._config)

    def _get_tracer_provider(self) -> ProxyTracerProvider:
        if self.__tracer_provider is None:
            self.__tracer_provider = self._config.get_tracer_provider()
        return self.__tracer_provider

    @contextmanager
    def _span(
        self,
        msg_template: LiteralString,
        *,
        span_name: str | None = None,
        **attributes: Any,
    ) -> Iterator[LogfireSpan]:
        stack_info = _get_caller_stack_info()

        merged_attributes = {**stack_info, **ATTRIBUTES.get(), **attributes}
        merged_attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] = msg_template

        tags = _merge_tags_into_attributes(merged_attributes, self._tags)

        span_name_: str
        log_message: str = msg_template
        if span_name is not None:
            span_name_ = span_name
        else:
            span_name_ = msg_template
        log_message = logfire_format(msg_template, {'span_name': span_name, **merged_attributes}, fallback='...')

        merged_attributes[ATTRIBUTES_MESSAGE_KEY] = log_message

        if self._spans_tracer is None:
            self._spans_tracer = self._get_tracer_provider().get_tracer(
                'logfire',  # the name here is really not important, logfire itself doesn't use it
            )

        otlp_attributes = user_attributes(merged_attributes)
        if tags:
            otlp_attributes[ATTRIBUTES_TAGS_KEY] = tags

        span = self._spans_tracer.start_span(
            name=span_name_,
            attributes=otlp_attributes,
        )

        with trace_api.use_span(span, end_on_exit=False, record_exception=False):
            logfire_span = LogfireSpan(span)
            with logfire_span.activate():
                try:
                    yield logfire_span
                finally:
                    current_attributes: Mapping[str, Any] = getattr(span, 'attributes', None) or {}
                    log_message = logfire_format(
                        # note that current_attributes may contain some of our json encoded attributes from user_attributes()
                        # which really should not exist as far as users are concerned, but users could
                        # technically grab these into their message template, we're not going to go our of our way to prevent that
                        msg_template,
                        {'span_name': span_name, **merged_attributes, **current_attributes},
                    )
                    span.set_attribute(ATTRIBUTES_MESSAGE_KEY, log_message)

    def span(
        self,
        msg_template: LiteralString,
        *,
        span_name: str | None = None,
        **attributes: Any,
    ) -> ContextManager[LogfireSpan]:
        """Context manager for creating a span.

        Args:
            msg_template: The template for the span message.
            span_name: The span name. If not provided, the rendered message will be used.
            attributes: The arguments to format the span message template with.

        ```py
        import logfire

        with logfire.span('This is a span {a=}', a='data'):
            logfire.info('new log 1')
        ```
        """
        return self._span(
            msg_template=msg_template,
            span_name=span_name,
            **attributes,
        )

    def instrument(
        self,
        msg_template: LiteralString | None = None,
        *,
        span_name: str | None = None,
        extract_args: bool | None = None,
    ) -> Callable[[Callable[_PARAMS, _RETURN]], Callable[_PARAMS, _RETURN]]:
        """Decorator for instrumenting a function as a span.

        Args:
            msg_template: The template for the span message. If not provided, the span name will be used.
            span_name: The name of the span. If not provided, the function name will be used.
            extract_args: Whether to extract arguments from the function signature and log them as span attributes.
                If not provided, this will be enabled if `msg_template` is provided and contains `{}`.

        ```py
        import logfire

        @logfire.instrument('This is a span {a=}')
        def my_function(a: int):
            logfire.info('new log {a=}', a=a)
        ```
        """
        if extract_args is None:
            extract_args = bool(msg_template and '{' in msg_template)

        def decorator(func: Callable[_PARAMS, _RETURN]) -> Callable[_PARAMS, _RETURN]:
            nonlocal span_name
            if span_name is None:
                if func.__module__:
                    span_name_ = f'{func.__module__}.{getattr(func, "__qualname__", func.__name__)}'
                else:
                    span_name_ = getattr(func, '__qualname__', func.__name__)
            else:
                span_name_ = span_name

            pos_params = ()
            if extract_args:
                sig = inspect_signature(func)
                pos_params = tuple(n for n, p in sig.parameters.items() if p.kind in _POSITIONAL_PARAMS)

            @wraps(func)
            def _instrument_wrapper(*args: _PARAMS.args, **kwargs: _PARAMS.kwargs) -> _RETURN:
                if extract_args:
                    pos_args = {k: v for k, v in zip(pos_params, args)}
                    extracted_kwargs = {**pos_args, **kwargs}
                else:
                    extracted_kwargs = {}

                with self._span(msg_template=msg_template, span_name=span_name_, **extracted_kwargs):  # type: ignore
                    return func(*args, **kwargs)

            return _instrument_wrapper

        return decorator

    def log(self, msg_template: LiteralString, /, level: LevelName, **attributes: Any) -> None:
        """Log a message.

        Args:
            msg_template: The message to log.
            level: The level of the log.
            attributes: The attributes to bind to the log.

        ```py
        import logfire

        logfire.log('This is a log', level='info')
        ```
        """

        stack_info = _get_caller_stack_info()

        merged_attributes = {**stack_info, **ATTRIBUTES.get(), **attributes}
        tags = _merge_tags_into_attributes(merged_attributes, self._tags) or []
        msg = logfire_format(msg_template, merged_attributes)
        otlp_attributes = user_attributes(merged_attributes)
        otlp_attributes = {
            ATTRIBUTES_SPAN_TYPE_KEY: 'log',
            ATTRIBUTES_LOG_LEVEL_KEY: level,
            ATTRIBUTES_MESSAGE_TEMPLATE_KEY: msg_template,
            ATTRIBUTES_MESSAGE_KEY: msg,
            **otlp_attributes,
        }
        if tags:
            otlp_attributes[ATTRIBUTES_TAGS_KEY] = tags

        start_time = self._config.ns_timestamp_generator()

        if self._logs_tracer is None:
            self._logs_tracer = self._get_tracer_provider().get_tracer(
                'logfire',  # the name here is really not important, logfire itself doesn't use it
                wrap_with_start_span_tracer=False,  # logs don't need a start span
            )

        span = self._logs_tracer.start_span(
            msg,
            attributes=otlp_attributes,
            start_time=start_time,
        )
        with trace_api.use_span(span, end_on_exit=False, record_exception=False):
            span.set_status(trace_api.Status(trace_api.StatusCode.OK))
            span.end(start_time)

    def debug(self, msg_template: LiteralString, /, **attributes: Any) -> None:
        """Log a debug message.

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.

        ```py
        import logfire

        logfire.debug('This is a debug log')
        ```
        """
        self.log(msg_template, 'debug', **attributes)

    def info(self, msg_template: LiteralString, /, **attributes: Any) -> None:
        """Log an info message.

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.

        ```py
        import logfire

        logfire.info('This is an info log')
        ```
        """
        self.log(msg_template, 'info', **attributes)

    def notice(self, msg_template: LiteralString, /, **attributes: Any) -> None:
        """Log a notice message.

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.

        ```py
        import logfire

        logfire.notice('This is a notice log')
        ```
        """
        self.log(msg_template, 'notice', **attributes)

    def warning(self, msg_template: LiteralString, /, **attributes: Any) -> None:
        """Log a warning message.

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.

        ```py
        import logfire

        logfire.warning('This is a warning log')
        ```
        """
        self.log(msg_template, 'warning', **attributes)

    def error(self, msg_template: LiteralString, /, **attributes: Any) -> None:
        """Log an error message.

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.

        ```py
        import logfire

        logfire.error('This is an error log')
        ```
        """
        self.log(msg_template, 'error', **attributes)

    def critical(self, msg_template: LiteralString, /, **attributes: Any) -> None:
        """Log a critical message.

        Args:
            msg_template: The message to log.
            attributes: The attributes to bind to the log.

        ```py
        import logfire

        logfire.critical('This is a critical log')
        ```
        """
        self.log(msg_template, 'critical', **attributes)

    def force_flush(self, timeout_millis: int = 3_000) -> bool:
        """Force flush all spans.

        Args:
            timeout_millis: The timeout in milliseconds.

        Returns:
            Whether the flush was successful.
        """
        return self._get_tracer_provider().force_flush(timeout_millis)


class LogfireSpan(ReadableSpan):
    def __init__(self, span: trace_api.Span) -> None:
        self._span = span
        self.end_on_exit = True

    if not TYPE_CHECKING:

        def __getattr__(self, name: str) -> Any:
            return getattr(self._span, name)

    @property
    def message_template(self) -> str | None:
        attributes = getattr(self._span, 'attributes')
        if not attributes:
            return None
        if ATTRIBUTES_MESSAGE_TEMPLATE_KEY not in attributes:
            return None
        return str(attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY])

    @property
    def tags(self) -> Sequence[str]:
        attributes = getattr(self._span, 'attributes')
        if not attributes:
            return []
        if ATTRIBUTES_TAGS_KEY not in attributes:
            return []
        return cast(Sequence[str], attributes[ATTRIBUTES_TAGS_KEY])

    def end(self) -> None:
        """Sets the current time as the span's end time.

        The span's end time is the wall time at which the operation finished.

        Only the first call to this method is recorded, further calls are ignored so you
        can call this within the span's context manager to end it before the context manager
        exits.
        """
        if self._span.is_recording():
            self._span.end()

    @contextmanager
    def activate(self, end_on_exit: bool | None = None) -> Iterator[None]:
        """
        Activates this span in the current context.

        Args:
            end_on_exit: Whether to end the span when the context manager exits, if `None` will use the value
                of self.end_on_exit.
                By setting end_on_exit=False when creating the span or assigning the attribute you can
                later use `activate` to manually activate and end the span.
        """
        with trace_api.use_span(self._span, end_on_exit=False, record_exception=False):
            with self._maybe_exit(end_on_exit):
                yield

    @staticmethod
    @contextmanager
    def _record_exception(span: trace_api.Span) -> Iterator[None]:
        """Context manager for recording an exception on a span.

        This will record the exception on the span and re-raise it.

        Args:
            span: The span to record the exception on.

        Raises:
            Any: The exception that was raised.
        """
        try:
            yield
        # NOTE: We don't want to catch `BaseException` here, since that would catch
        # things like `KeyboardInterrupt` and `SystemExit`. Also, `Exception` is the one caught
        # by the `tracer.use_span` context manager internally.
        except Exception as exc:
            if span.is_recording():
                # stolen from OTEL's codebase
                span.set_status(
                    trace_api.Status(
                        status_code=trace_api.StatusCode.ERROR,
                        description=f'{type(exc).__name__}: {exc}',
                    )
                )
                # insert a more detailed breakdown of pydantic errors
                tb = rich.traceback.Traceback.from_exception(
                    exc_type=type(exc), exc_value=exc, traceback=exc.__traceback__
                )
                tb.trace.stacks = [_filter_frames(stack) for stack in tb.trace.stacks]
                attributes: dict[str, otel_types.AttributeValue] = {
                    'exception.logfire.trace': json_dumps_traceback(tb.trace),
                }
                if ValidationError is not None and isinstance(exc, ValidationError):
                    err_json = exc.json(include_url=False)
                    span.set_attribute(ATTRIBUTES_VALIDATION_ERROR_KEY, exc.json(include_url=False))
                    attributes[ATTRIBUTES_VALIDATION_ERROR_KEY] = err_json
                span.record_exception(exc, attributes=attributes, escaped=True)
            raise
        else:
            if span.is_recording():
                span.set_status(
                    trace_api.Status(
                        status_code=trace_api.StatusCode.OK,
                    )
                )

    @contextmanager
    def _maybe_exit(self, end_on_exit: bool | None = None) -> Iterator[None]:
        """Context manager that ends a span on exit.

        Args:
            end_on_exit: Whether to end the span when the context manager exits, if `None` will use
                the value of self.end_on_exit.
        """
        try:
            with self._record_exception(self._span):
                yield
        finally:
            end_on_exit_ = self.end_on_exit if end_on_exit is None else end_on_exit
            if end_on_exit_:
                self._span.end()

    def set_attribute(self, key: str, value: otel_types.AttributeValue) -> None:
        """Sets an attribute on the span.

        Args:
            key: The key of the attribute.
            value: The value of the attribute.
        """
        self._span.set_attribute(key, value)


ATTRIBUTES: ContextVar[dict[str, Any]] = ContextVar('logfire.attributes', default={})


@contextmanager
@staticmethod
def with_attributes(**attributes: Any) -> Iterator[None]:
    """Context manager for binding attributes to all logs and traces.

    Args:
        attributes: The attributes to bind.

    ```py
    import logfire

    with logfire.with_attributes(user_id='123'):
        logfire.info('new log 1')
    ```
    """
    old_attributes = ATTRIBUTES.get()
    ATTRIBUTES.set({**old_attributes, **attributes})
    try:
        yield
    finally:
        ATTRIBUTES.set(old_attributes)


@contextmanager
@staticmethod
def with_tags(*tags: str) -> Iterator[None]:
    """Context manager for binding tags to all logs and traces.

    Args:
        tags: The tags to bind.

    ```py
    import logfire

    with logfire.with_tags('tag1', 'tag2'):
        logfire.info('new log 1')
    ```
    """
    old_attributes = ATTRIBUTES.get()
    merged_tags = _merge_tags_into_attributes(old_attributes, list(tags))
    if merged_tags:
        ATTRIBUTES.set({**old_attributes, ATTRIBUTES_TAGS_KEY: merged_tags})
    try:
        yield
    finally:
        ATTRIBUTES.set(old_attributes)


AttributesValueType = TypeVar('AttributesValueType', bound=Any | otel_types.AttributeValue)


def _merge_tags_into_attributes(attributes: dict[str, Any], tags: list[str]) -> list[str] | None:
    # merge tags into attributes preserving any existing tags
    if not tags:
        return None
    if ATTRIBUTES_TAGS_KEY in attributes:
        return cast('list[str]', attributes[ATTRIBUTES_TAGS_KEY]) + tags
    return tags


def user_attributes(attributes: dict[str, Any], should_flatten: bool = True) -> dict[str, otel_types.AttributeValue]:
    """Prepare attributes for sending to OpenTelemetry.

    This will convert any non-OpenTelemetry compatible types to JSON.
    """
    prepared: dict[str, otel_types.AttributeValue] = {}
    null_args: list[str] = []

    for key, value in attributes.items():
        if value is None:
            null_args.append(key)
        elif isinstance(value, (str, bool, int, float)):
            prepared[key] = value
        elif isinstance(value, Flatten) and should_flatten:
            value = cast(Flatten[Mapping[Any, Any] | Sequence[Any]], value).value
            iter = value.items() if isinstance(value, Mapping) else enumerate(value)
            for k, v in iter:
                inner_prepared = user_attributes({str(k): v}, should_flatten=False)
                for inner_key, inner_value in inner_prepared.items():
                    prepared[f'{key}.{inner_key}'] = inner_value
        else:
            prepared[key + NON_SCALAR_VAR_SUFFIX] = logfire_json_dumps(value)

    if null_args:
        prepared[NULL_ARGS_KEY] = tuple(null_args)

    return prepared


def _get_caller_stack_info() -> dict[str, otel_types.AttributeValue]:
    """Get the stack info of the caller.

    This is used to bind the caller's stack info to logs and spans.

    Returns:
        A dictionary of stack info attributes.
    """
    try:
        frame = inspect.currentframe()
        if frame is None:
            return {}
        stack = inspect.getouterframes(frame, 3)
        if len(stack) < 4:
            return {}
        caller_frame = stack[3]
        file = Path(caller_frame.filename)
        if file.is_absolute():
            try:
                file = file.relative_to(_CDW)
            except ValueError:
                # happens if filename path is not within CWD
                pass
        return {
            'code.filepath': str(file),
            'code.lineno': caller_frame.lineno,
            'code.function': caller_frame.function,
        }
    except Exception:
        return {}


def _filter_frames(stack: rich.traceback.Stack) -> rich.traceback.Stack:
    """
    filter out the record_exception call itself.
    """
    stack.frames = [f for f in stack.frames if not (f.filename.endswith('logfire/_main.py') and f.name.startswith('_'))]
    return stack


_RETURN = TypeVar('_RETURN')
_PARAMS = ParamSpec('_PARAMS')
_POSITIONAL_PARAMS = {SignatureParameter.POSITIONAL_ONLY, SignatureParameter.POSITIONAL_OR_KEYWORD}
