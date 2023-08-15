import base64
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cached_property, wraps
from inspect import Parameter as SignatureParameter, signature as inspect_signature
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypedDict, TypeVar

import httpx
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.common._internal import _encode_span_id
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Span, Tracer
from opentelemetry.util.types import AttributeValue
from pydantic import Field, TypeAdapter
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import LiteralString

from logfire.exporters.http import HttpJsonSpanExporter
from logfire.formatter import logfire_format
from logfire.secret import get_or_generate_secret

LEVEL_KEY = 'logfire.level'
MSG_TEMPLATE_KEY = 'logfire.msg_template'
LOG_TYPE_KEY = 'logfire.log_type'
TAGS_KEY = 'logfire.tags'
START_PARENT_ID = 'logfire.start_parent_id'
LevelName = Literal['debug', 'info', 'notice', 'warning', 'error', 'critical']

_RETURN = TypeVar('_RETURN')
_PARAMS = ParamSpec('_PARAMS')
_POSITIONAL_PARAMS = {SignatureParameter.POSITIONAL_ONLY, SignatureParameter.POSITIONAL_OR_KEYWORD}


class LogfireConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='LOGFIRE_')

    api_root: str = 'http://localhost:4318'
    web_root: str = 'http://localhost:3000'  # TODO: Load this value from the backend, or something like that
    project_id: str = Field(default_factory=get_or_generate_secret)
    service_name: str = 'logfire'
    verbose: bool = False

    auto_initialize_project: bool = True

    @property
    def projects_endpoint(self) -> str:
        return f'{self.api_root}/v1/projects/{self.project_id}'

    @property
    def traces_endpoint(self) -> str:
        return f'{self.api_root}/v1/traces/{self.project_id}'

    @property
    def web_endpoint(self) -> str:
        return f'{self.web_root}/logs/{self.project_id}'


class _Telemetry:
    def __init__(self, config: LogfireConfig):
        self._config = config

        self.service_name = service_name = config.service_name
        self.self_log(f'Configuring telemetry for {service_name!r}...')
        self.set_exporter(HttpJsonSpanExporter(endpoint=config.traces_endpoint))

        if config.auto_initialize_project:
            httpx.post(config.projects_endpoint)

        print(f'*** View logs at {config.web_endpoint} ***')

    def set_exporter(self, exporter: SpanExporter | None = None) -> None:
        self.provider = TracerProvider(resource=Resource(attributes={'service.name': self.service_name}))
        self.self_log(f'Configured tracer provider with service.name={self.service_name!r}')
        exporter = exporter or HttpJsonSpanExporter(endpoint=self._config.traces_endpoint)
        # TODO may want to make some of the processor options configurable so
        # that overhead vs latency tradeoff can be adjusted, for now set for
        # minimum latency which will be nicest on small workloads
        self.processor = BatchSpanProcessor(exporter, schedule_delay_millis=1)

        # FIXME big hack - without this `set_exporter` actually just adds another exporter!
        self.provider._active_span_processor._span_processors = ()

        self.provider.add_span_processor(self.processor)
        self.self_log(f'Configured span exporter with endpoint={self._config.traces_endpoint!r}')

    def self_log(self, __msg: str) -> None:
        # TODO: probably want to make this more configurable/etc.
        if self._config.verbose:
            print(__msg)


class LogFireSpan(TypedDict):
    real_span: Span
    start_span: Span


class Observe:
    def __init__(self, config: LogfireConfig | None = None):
        self._tracer: ContextVar[Tracer | None] = ContextVar('_tracer', default=None)
        self._config: LogfireConfig = config or LogfireConfig()
        self._tags: tuple[str, ...] = ()

    @cached_property
    def _telemetry(self) -> _Telemetry:
        # TODO: Don't allow modifying self._config once this has been initialized, or at least reset the cache
        return _Telemetry(self._config)

    # Configuration
    def configure(self, config: LogfireConfig | None = None, exporter: SpanExporter | None = None) -> None:
        if config is not None:
            self._config = config

        # Clear and recompute the cached property
        self.__dict__.pop('_telemetery', None)
        assert self._telemetry
        self._telemetry.set_exporter(exporter)

    # Tags
    def tags(self, first_tag: str, /, *more_tags: str) -> 'TaggedObserve':
        return TaggedObserve((first_tag,) + more_tags, self)

    def _set_tags(self, tags: tuple[str, ...]) -> None:
        self._tags = tags

    def _get_tags(self) -> tuple[str, ...] | None:
        if not self._tags:
            return None
        tags = self._tags
        self._tags = ()
        return tags

    # Spans
    @contextmanager
    def span(self, span_name: str, msg_template: LiteralString, /, **kwargs: Any) -> Iterator[LogFireSpan]:
        tracer = self._get_context_tracer()
        span_start = int(time.time() * 1e9)

        start_parent_id = self._start_parent_id()
        attrs: dict[str, AttributeValue] = {LOG_TYPE_KEY: 'real_span'}
        if tags := self._get_tags():
            attrs[TAGS_KEY] = tags
        real_span: Span
        with tracer.start_as_current_span(span_name, attributes=attrs, start_time=span_start) as real_span:
            start_span = self._span_start(tracer, start_parent_id, span_start, msg_template, kwargs)

            yield {'real_span': real_span, 'start_span': start_span}

    def instrument(
        self,
        msg_template: LiteralString | None = None,
        *,
        span_name: str | None = None,
        extract_args: bool | None = None,
    ) -> Callable[[Callable[_PARAMS, _RETURN]], Callable[_PARAMS, _RETURN]]:
        tracer = self._get_context_tracer()

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
            def wrapper(*args: _PARAMS.args, **kwargs: _PARAMS.kwargs) -> _RETURN:
                span_start = int(time.time() * 1e9)

                if extract_args:
                    pos_args = {k: v for k, v in zip(pos_params, args)}
                    kwarg_groups: tuple[dict[str, Any], ...] = pos_args, kwargs
                else:
                    kwarg_groups = ()

                start_parent_id = self._start_parent_id()
                attrs: dict[str, AttributeValue] = {LOG_TYPE_KEY: 'real_span'}
                if tags := self._get_tags():
                    attrs[TAGS_KEY] = tags
                with tracer.start_as_current_span(span_name_, attributes=attrs, start_time=span_start):
                    self._span_start(tracer, start_parent_id, span_start, msg_template or span_name_, *kwarg_groups)
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    # Logging
    def log(self, msg_template: LiteralString, level: LevelName, kwargs: Any) -> None:
        msg = logfire_format(msg_template, kwargs)
        tracer = self._get_context_tracer()
        start_end_time = int(time.time() * 1e9)  # OpenTelemetry uses ns for timestamps

        attributes = self._prepare_attributes(kwargs)
        attributes[LEVEL_KEY] = level
        attributes[MSG_TEMPLATE_KEY] = msg_template
        attributes[LOG_TYPE_KEY] = 'log'
        if tags := self._get_tags():
            attributes[TAGS_KEY] = tags

        span = tracer.start_span(
            name=msg,
            start_time=start_end_time,
            attributes=attributes,
        )
        span.end(start_end_time)
        with trace.use_span(span):
            pass

    def debug(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'debug', kwargs)

    def info(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'info', kwargs)

    def notice(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'notice', kwargs)

    def warning(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'warning', kwargs)

    def error(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'error', kwargs)

    def critical(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
        self.log(msg_template, 'critical', kwargs)

    # Utilities
    @contextmanager
    def context_tracer(self, name: str) -> Iterator[None]:
        tracer = self._get_tracer(name)
        token = self._tracer.set(tracer)
        try:
            yield
        finally:
            self._tracer.reset(token)

    @staticmethod
    def _start_parent_id() -> str | None:
        id_int = trace.get_current_span(None).get_span_context().span_id
        if id_int == 0:
            return None
        else:
            # this matches what OTel does internally to convert int span ids into strings
            return base64.b64encode(_encode_span_id(id_int)).decode()

    def _span_start(
        self,
        tracer: Tracer,
        outer_parent_id: str | None,
        span_start: int,
        msg_template: str,
        *kwarg_groups: dict[str, Any],
    ) -> Span:
        """Send a zero length span at the start of the main span to represent the span opening.

        This is required since the span itself isn't sent until it's closed.
        """
        msg = logfire_format(msg_template, *kwarg_groups)
        start_attrs: dict[str, AttributeValue] = {
            MSG_TEMPLATE_KEY: msg_template,
            LOG_TYPE_KEY: 'start_span',
        }
        if outer_parent_id is not None:
            start_attrs[START_PARENT_ID] = outer_parent_id
        for kw in kwarg_groups:
            if kw:
                start_attrs.update(self._prepare_attributes(kw))

        start_span: Span = tracer.start_span(
            name=msg,
            start_time=span_start,
            attributes=start_attrs,
        )
        start_span.end(span_start)
        with trace.use_span(start_span):
            pass

        return start_span

    def _get_context_tracer(self) -> Tracer:
        tracer = self._tracer.get()
        if tracer is None:
            # raise RuntimeError('No tracer set')
            return self._get_tracer(self._config.service_name)
        return tracer

    def _get_tracer(self, name: str) -> Tracer:
        # TODO: Add version, schema_url?
        return trace.get_tracer(name, tracer_provider=self._telemetry.provider)

    def _prepare_attributes(self, attributes: dict[str, Any]) -> dict[str, AttributeValue]:
        prepared: dict[str, AttributeValue] = {}

        for k, v in attributes.items():
            self._set_prepared_attribute(prepared, k, v, '')

        return prepared

    def _set_prepared_attribute(
        self,
        target: dict[str, AttributeValue],
        key: str,
        value: Any,
        prefix: str,
        dumped: bool = False,
    ) -> None:
        prefixed_key = prefix + key
        if isinstance(value, str | bool | int | float):
            target[prefixed_key] = value
        elif isinstance(value, list):
            # TODO: validate that the list is opentelemetry-compatible
            #   Need to decide exactly what to do if it isn't
            target[prefixed_key] = value
        elif isinstance(value, dict):
            for k, v in value.items():
                self._set_prepared_attribute(target, k, v, f'{prefixed_key}.')
        elif not dumped:
            dumped_value = _ANY_TYPE_ADAPTER.dump_python(value)
            self._set_prepared_attribute(target, key, dumped_value, prefix, dumped=True)
        else:
            raise TypeError(f'Unsupported type {type(value)} for attribute {key}')

    def _self_log(self, __msg: str) -> None:
        self._telemetry.self_log(__msg)


class TaggedObserve:
    """Proxy class to to make the observer.tags() syntax possible."""

    def __init__(self, tags: tuple[str, ...], observe: Observe):
        self._tags = tags
        self._observe = observe

    if TYPE_CHECKING:

        @contextmanager
        def span(self, span_name: str, msg_template: LiteralString, /, **kwargs: Any) -> Iterator[LogFireSpan]:
            pass

        def instrument(
            self,
            tracer_name: str | None = None,
            span_name: str | None = None,
            msg_template: LiteralString | None = None,
            inspect: bool = False,
        ) -> Callable[[Callable[_PARAMS, _RETURN]], Callable[_PARAMS, _RETURN]]:
            pass

        def log(self, msg_template: LiteralString, level: LevelName, kwargs: Any) -> None:
            pass

        def debug(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            pass

        def info(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            pass

        def notice(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            pass

        def warning(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            pass

        def error(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            pass

        def critical(self, msg_template: LiteralString, /, **kwargs: Any) -> None:
            pass

    else:

        def __getattr__(self, item):
            self._observe._set_tags(self._tags)
            return getattr(self._observe, item)

    def tags(self, first_tag: str, *args: str) -> 'TaggedObserve':
        return TaggedObserve(self._tags + (first_tag,) + tuple(args), self._observe)


_ANY_TYPE_ADAPTER = TypeAdapter(Any)
