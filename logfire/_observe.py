# TODO(Samuel) rename to `_main`
from __future__ import annotations as _annotations

import json
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cached_property, wraps
from inspect import Parameter as SignatureParameter, signature as inspect_signature
from pathlib import Path
from types import FrameType, TracebackType
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypeVar, cast

import rich.traceback
from opentelemetry import propagate, trace
from opentelemetry.context import Context as OtelContext
from opentelemetry.sdk.trace import Tracer
from opentelemetry.util.types import AttributeValue
from typing_extensions import LiteralString

from ._json_encoder import json_dumps_traceback, logfire_json_dumps
from .config import LogfireConfig
from .formatter import logfire_format

try:
    from pydantic_core import ValidationError as PydanticValidationError
except ImportError:
    # pydantic is not installed, this is possible since it's not a dependency
    PydanticValidationError = None

__all__ = 'Logfire', 'LogfireContext', 'LogfireSpan', 'TaggedLogfire'

LEVEL_KEY = 'logfire.level'
MSG_TEMPLATE_KEY = 'logfire.msg_template'
LOG_TYPE_KEY = 'logfire.log_type'
TAGS_KEY = 'logfire.tags'
NULL_ARGS_KEY = 'logfire.null_args'
START_PARENT_ID = 'logfire.start_parent_id'
LINENO = 'logfire.lineno'
FILENAME = 'logfire.filename'
NON_SCALAR_VAR_SUFFIX = '__JSON'
LevelName = Literal['debug', 'info', 'notice', 'warning', 'error', 'critical']
LogTypeType = Literal['log', 'start_span', 'real_span']

_RETURN = TypeVar('_RETURN')
_PARAMS = ParamSpec('_PARAMS')
_POSITIONAL_PARAMS = {SignatureParameter.POSITIONAL_ONLY, SignatureParameter.POSITIONAL_OR_KEYWORD}

_cwd = Path('.').resolve()


class Logfire:
    def __init__(self, config: LogfireConfig | None = None):
        self._tracer: ContextVar[Tracer | None] = ContextVar('_tracer', default=None)
        self._init_config: LogfireConfig | None = config
        self._tags: tuple[str, ...] = ()

    def tags(self, first_tag: str, /, *more_tags: str) -> TaggedLogfire:
        return TaggedLogfire((first_tag,) + more_tags, self)

    # Spans
    @contextmanager
    def span(
        self, msg_template: LiteralString, *, span_name: str | None = None, **kwargs: Any
    ) -> Iterator[LogfireSpan]:
        """Context manager for creating a span."""
        tracer = self.get_context_tracer()
        start_time = int(time.time() * 1e9)

        span_name_: str
        if span_name is not None:
            span_name_ = span_name
            kwargs['span_name'] = span_name
        else:
            span_name_ = logfire_format(msg_template, kwargs)

        start_parent_id = self._start_parent_id()
        logfire_attributes = self._logfire_attributes('real_span', start_parent_id=start_parent_id)

        real_span = tracer.start_span(
            span_name_, attributes=logfire_attributes, start_time=start_time, record_exception=False
        )

        # we don't use LogfireSpan.active here to avoid adding another entry to the stack on exceptions
        with trace.use_span(real_span, end_on_exit=False, record_exception=False):
            start_span = self._span_start(
                tracer=tracer,
                outer_parent_id=start_parent_id,
                start_time=start_time,
                msg_template=msg_template,
                kwargs=kwargs,
            )
            logfire_span = LogfireSpan(real_span, start_span)
            with maybe_exit(logfire_span):
                yield logfire_span

    def instrument(
        self,
        msg_template: LiteralString | None = None,
        *,
        span_name: str | None = None,
        extract_args: bool | None = None,
    ) -> Callable[[Callable[_PARAMS, _RETURN]], Callable[_PARAMS, _RETURN]]:
        """Decorator for instrumenting a function as a span."""
        tracer = self.get_context_tracer()

        if extract_args is None:
            extract_args = bool(msg_template and '{' in msg_template)

        def decorator(func: Callable[_PARAMS, _RETURN]) -> Callable[_PARAMS, _RETURN]:
            nonlocal span_name
            if span_name is None:
                span_name_ = f'{func.__module__}.{func.__name__}'
            else:
                span_name_ = span_name
            self._self_log(f'Instrumenting {func=} {span_name=}')

            if extract_args:
                sig = inspect_signature(func)
                pos_params = tuple(n for n, p in sig.parameters.items() if p.kind in _POSITIONAL_PARAMS)

            @wraps(func)
            def instrument_wrapper(*args: _PARAMS.args, **kwargs: _PARAMS.kwargs) -> _RETURN:
                start_time = int(time.time() * 1e9)

                if extract_args:
                    pos_args = {k: v for k, v in zip(pos_params, args)}
                    extracted_kwargs = {**pos_args, **kwargs}
                else:
                    extracted_kwargs = {}

                start_parent_id = self._start_parent_id()
                attributes = self._logfire_attributes('real_span')
                with tracer.start_as_current_span(
                    span_name_, attributes=attributes, start_time=start_time, record_exception=False
                ) as real_span:
                    self._span_start(
                        tracer=tracer,
                        outer_parent_id=start_parent_id,
                        start_time=start_time,
                        msg_template=msg_template or span_name_,
                        kwargs=extracted_kwargs,
                    )
                    with record_exception(real_span):
                        return func(*args, **kwargs)

            return instrument_wrapper

        return decorator

    # Logging
    def log(
        self,
        msg_template: LiteralString,
        level: LevelName,
        kwargs: Any,
        frame_depth: int = 1,
        context: LogfireContext | None = None,
    ) -> None:
        msg = logfire_format(msg_template, kwargs)
        tracer = self.get_context_tracer()
        start_time = int(time.time() * 1e9)  # OpenTelemetry uses ns for timestamps

        call_frame: FrameType = sys._getframe(frame_depth)  # type: ignore
        lineno = call_frame.f_lineno
        file = Path(call_frame.f_code.co_filename)
        if file.is_absolute():
            try:
                file = file.relative_to(_cwd)
            except ValueError:
                # happens if filename path is not within CWD
                pass

        user_attributes = self.user_attributes(kwargs)
        logfire_attributes = self._logfire_attributes(
            'log', msg_template=msg_template, level=level, lineno=lineno, filename=str(file)
        )
        attributes = {**user_attributes, **logfire_attributes}

        otel_context = context.otel_context if context is not None else None
        span = tracer.start_span(name=msg, start_time=start_time, attributes=attributes, context=otel_context)
        span.end(start_time)
        with trace.use_span(span):
            pass

    def debug(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'debug', kwargs, frame_depth=2)

    def info(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'info', kwargs, frame_depth=2)

    def notice(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'notice', kwargs, frame_depth=2)

    def warning(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'warning', kwargs, frame_depth=2)

    def error(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'error', kwargs, frame_depth=2)

    def critical(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'critical', kwargs, frame_depth=2)

    @classmethod
    def get_context(cls) -> LogfireContext:
        carrier: OtelContext = {}  # type: ignore
        propagate.inject(carrier)
        return LogfireContext(otel_context=carrier)

    # Utilities
    @contextmanager
    def context_tracer(self, name: str) -> Iterator[None]:
        tracer = self._get_tracer(name)
        token = self._tracer.set(tracer)
        try:
            yield
        finally:
            self._tracer.reset(token)

    @cached_property
    def _config(self) -> LogfireConfig:
        if self._init_config is not None:
            return self._init_config
        else:
            return LogfireConfig.get_default()

    @staticmethod
    def _start_parent_id() -> str | None:
        span_id = trace.get_current_span(None).get_span_context().span_id
        if span_id == 0:
            return None
        return trace.format_span_id(span_id)

    def _span_start(
        self,
        *,
        tracer: Tracer,
        outer_parent_id: str | None,
        start_time: int,
        msg_template: str,
        kwargs: dict[str, Any],
    ) -> trace.Span:
        """Send a zero length span at the start of the main span to represent the span opening.

        This is required since the span itself isn't sent until it's closed.
        """
        msg = logfire_format(msg_template, kwargs)

        logfire_attributes = self._logfire_attributes(
            'start_span', msg_template=msg_template, start_parent_id=outer_parent_id
        )
        user_attributes = self.user_attributes(kwargs)
        attributes = {**logfire_attributes, **user_attributes}

        start_span = tracer.start_span(name=msg, start_time=start_time, attributes=attributes)
        start_span.end(start_time)
        with trace.use_span(start_span):
            pass

        return start_span

    def get_context_tracer(self) -> Tracer:
        tracer = self._tracer.get()
        if tracer is None:
            return self._get_tracer(self._config.service_name)
        return tracer

    def _get_tracer(self, name: str) -> Tracer:
        # NOTE(DavidM): Should we add version, schema_url?
        return trace.get_tracer(name, tracer_provider=self._config.provider)  # type: ignore

    def _logfire_attributes(
        self,
        log_type: LogTypeType,
        *,
        msg_template: str | None = None,
        level: LevelName | None = None,
        start_parent_id: str | None = None,
        lineno: int | None = None,
        filename: str | None = None,
    ) -> dict[str, AttributeValue]:
        tags = self._pop_tags()
        return _dict_not_none(
            **{
                LOG_TYPE_KEY: log_type,
                LEVEL_KEY: level,
                MSG_TEMPLATE_KEY: msg_template,
                TAGS_KEY: tags,
                START_PARENT_ID: start_parent_id,
                LINENO: lineno,
                FILENAME: filename,
            }
        )

    @staticmethod
    def user_attributes(attributes: dict[str, Any]) -> dict[str, AttributeValue]:
        """Prepare attributes for sending to OpenTelemetry.

        This will convert any non-OpenTelemetry compatible types to JSON.
        """
        prepared: dict[str, AttributeValue] = {}
        null_args: list[str] = []

        for key, value in attributes.items():
            match value:
                case None:
                    null_args.append(key)
                case str() | bool() | int() | float():
                    prepared[key] = value
                case _:
                    prepared[key + NON_SCALAR_VAR_SUFFIX] = logfire_json_dumps(value)

        if null_args:
            prepared[NULL_ARGS_KEY] = tuple(null_args)

        return prepared

    def _set_tags(self, tags: tuple[str, ...]) -> None:
        self._tags = tags

    def _pop_tags(self) -> tuple[str, ...] | None:
        if not self._tags:
            return None
        tags = self._tags
        self._tags = ()
        return tags

    def _self_log(self, __msg: str) -> None:
        # TODO: probably want to make this more configurable/etc.
        if self._config.internal_logging:
            print(__msg)


class TaggedLogfire:
    """Proxy class to make the logfire.tags() syntax possible."""

    def __init__(self, tags: tuple[str, ...], observe: Logfire):
        self._tags = tags
        self._logfire_logger = observe

    if TYPE_CHECKING:

        @contextmanager
        def span(
            self, msg_template: LiteralString, *, span_name: str | None = None, **kwargs: Any
        ) -> Iterator[LogfireSpan]:
            ...

        def instrument(
            self,
            tracer_name: str | None = None,
            span_name: str | None = None,
            msg_template: LiteralString | None = None,
            inspect: bool = False,
        ) -> Callable[[Callable[_PARAMS, _RETURN]], Callable[_PARAMS, _RETURN]]:
            ...

        def log(self, msg_template: LiteralString, level: LevelName, kwargs: Any) -> None:
            ...

        def debug(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

        def info(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

        def notice(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

        def warning(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

        def error(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

        def critical(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            ...

    else:

        def __getattr__(self, item):
            self._logfire_logger._set_tags(self._tags)
            return getattr(self._logfire_logger, item)

    def tags(self, first_tag: str, *args: str) -> TaggedLogfire:
        return TaggedLogfire(self._tags + (first_tag,) + tuple(args), self._logfire_logger)


@dataclass(slots=True)
class LogfireSpan:
    """
    Logfire span, holds references to both our `real_span` and `start_span`.
    """

    real_span: trace.Span
    """
    `real_span` is the open telemetry span used to represent the span, it's so named to differentiate it from
    `start_span`, `real_span`'s length is the actual length of the span and it's send when the space ends.
    """
    start_span: trace.Span | None
    """
    `start_span` contains information about the message that started the span, it's a zero length and is sent
    right after the span starts, it allows us to "see" the span while it's still open.
    """
    end_on_exit: bool = True
    """
    Switch to control whether the span should be ended when the context manager exits, this allows you to
    re-activate and re-use the span multiple times
    """

    def end(self) -> None:
        self.real_span.end()

    @contextmanager
    def activate(self, end_on_exit: bool | None = None) -> Iterator[None]:
        """
        Activates this span in the current context.

        Args:
            end_on_exit: Whether to end the span when the context manager exits, if `None` will use the value
                of `self.end_on_exit`, this allows you to avoid ending the span withing a context manager.
        """
        with trace.use_span(self.real_span, end_on_exit=False, record_exception=False):
            with maybe_exit(self, end_on_exit):
                yield


@contextmanager
def maybe_exit(logfire_span: LogfireSpan, end_on_exit: bool | None = None) -> Iterator[None]:
    try:
        with record_exception(logfire_span.real_span):
            yield
    finally:
        end_on_exit_ = logfire_span.end_on_exit if end_on_exit is None else end_on_exit
        if end_on_exit_:
            logfire_span.end()


@dataclass(slots=True)
class LogfireContext:
    """
    Wrapper for context as propagated by OpenTelemetry, done this way so we can change the type without
    breaking the public API.

    See https://opentelemetry.io/docs/specs/otel/context/
    """

    otel_context: OtelContext

    def to_json(self) -> str:
        return logfire_json_dumps(self.otel_context)

    @classmethod
    def from_json(cls, json_data: str | bytes) -> LogfireContext:
        return cls(**json.loads(json_data))


@contextmanager
def record_exception(span: trace.Span) -> Iterator[None]:
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
    except Exception:
        exc_type, exc_value, traceback = cast(tuple[type[Exception], Exception, TracebackType], sys.exc_info())
        # NOTE(Marcelo): You can pass `show_locals=True` to `rich.traceback.Traceback.from_exception`
        # to get the local variables in the traceback. For now, we're not doing that.
        tb = rich.traceback.Traceback.from_exception(exc_type=exc_type, exc_value=exc_value, traceback=traceback)

        tb.trace.stacks = [_filter_frames(stack) for stack in tb.trace.stacks]

        attributes: dict[str, str] = {
            'exception.logfire.trace': json_dumps_traceback(tb.trace),
            'exception.logfire.data': '',
        }
        if PydanticValidationError is not None and exc_type == PydanticValidationError:
            exc = cast(PydanticValidationError, exc_value)
            attributes['exception.logfire.data'] = logfire_json_dumps({'errors': exc.errors(include_url=False)})

        span.record_exception(exc_value, attributes=attributes, escaped=True)
        raise


IGNORED_METHODS: set[str] = {'record_exception', 'instrument_wrapper', 'maybe_exit'}


def _filter_frames(stack: rich.traceback.Stack) -> rich.traceback.Stack:
    """
    filter out the record_exception call itself.
    """
    stack.frames = [
        f for f in stack.frames if not (f.filename.endswith('logfire/_observe.py') and f.name in IGNORED_METHODS)
    ]
    return stack


def _dict_not_none(**kwargs: Any) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}
