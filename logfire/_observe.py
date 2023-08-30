import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cached_property, wraps
from inspect import Parameter as SignatureParameter, signature as inspect_signature
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypedDict, TypeVar

import httpx
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Span, Tracer, format_span_id
from opentelemetry.util.types import AttributeValue
from pydantic import Field, TypeAdapter
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import LiteralString

from logfire.exporters.http import HttpJsonSpanExporter, _dict_not_none  # type: ignore
from logfire.formatter import logfire_format
from logfire.secret import get_or_generate_secret

LEVEL_KEY = 'logfire.level'
MSG_TEMPLATE_KEY = 'logfire.msg_template'
LOG_TYPE_KEY = 'logfire.log_type'
TAGS_KEY = 'logfire.tags'
START_PARENT_ID = 'logfire.start_parent_id'
NON_SCALAR_VAR_SUFFIX = '__JSON'
LevelName = Literal['debug', 'info', 'notice', 'warning', 'error', 'critical']
LogTypeType = Literal['log', 'start_span', 'real_span']

_RETURN = TypeVar('_RETURN')
_PARAMS = ParamSpec('_PARAMS')
_POSITIONAL_PARAMS = {SignatureParameter.POSITIONAL_ONLY, SignatureParameter.POSITIONAL_OR_KEYWORD}


class LogfireConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='LOGFIRE_')

    api_root: str = 'http://localhost:4318'
    project_id: str = Field(default_factory=get_or_generate_secret)
    service_name: str = 'logfire'
    verbose: bool = False

    # TODO(Marcelo): This should be removed with the new API.
    # https://linear.app/pydantic/issue/PYD-246/logfire-sdk-setup.
    auto_initialize_project: bool = True

    @property
    def projects_endpoint(self) -> str:
        return f'{self.api_root}/v1/projects/{self.project_id}'

    @property
    def traces_endpoint(self) -> str:
        return f'{self.api_root}/v1/traces/{self.project_id}'


class _Telemetry:
    def __init__(self, config: LogfireConfig):
        self._config = config

        self.service_name = service_name = config.service_name
        self.self_log(f'Configuring telemetry for {service_name!r}...')
        self.set_exporter(HttpJsonSpanExporter(endpoint=config.traces_endpoint))

        if config.auto_initialize_project:
            self.initialize_project()

    def initialize_project(self) -> None:
        response = httpx.post(self._config.projects_endpoint)
        response.raise_for_status()
        dashboard_url = response.json()['dashboard_url']
        print(f'*** View logs at {dashboard_url} ***')

    def set_exporter(self, exporter: SpanExporter | None = None) -> None:
        self.provider = TracerProvider(resource=Resource(attributes={'service.name': self.service_name}))
        self.self_log(f'Configured tracer provider with service.name={self.service_name!r}')
        exporter = exporter or HttpJsonSpanExporter(endpoint=self._config.traces_endpoint)
        # TODO may want to make some of the processor options configurable so
        # that overhead vs latency tradeoff can be adjusted, for now set for
        # minimum latency which will be nicest on small workloads
        self.processor = BatchSpanProcessor(exporter, schedule_delay_millis=1)

        # FIXME big hack - without this `set_exporter` actually just adds another exporter!
        self.provider._active_span_processor._span_processors = ()  # type: ignore

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
        """Context manager for creating a span."""
        tracer = self._get_context_tracer()
        start_time = int(time.time() * 1e9)

        start_parent_id = self._start_parent_id()
        logfire_attributes = self._logfire_attributes('real_span', start_parent_id=start_parent_id)
        with tracer.start_as_current_span(span_name, attributes=logfire_attributes, start_time=start_time) as real_span:
            start_span = self._span_start(tracer, start_parent_id, start_time, msg_template, kwargs)

            yield {'real_span': real_span, 'start_span': start_span}

    def instrument(
        self,
        msg_template: LiteralString | None = None,
        *,
        span_name: str | None = None,
        extract_args: bool | None = None,
    ) -> Callable[[Callable[_PARAMS, _RETURN]], Callable[_PARAMS, _RETURN]]:
        """Decorator for instrumenting a function as a span."""
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
                start_time = int(time.time() * 1e9)

                if extract_args:
                    pos_args = {k: v for k, v in zip(pos_params, args)}
                    kwarg_groups: tuple[dict[str, Any], ...] = pos_args, kwargs
                else:
                    kwarg_groups = ()

                start_parent_id = self._start_parent_id()
                attributes = self._logfire_attributes('real_span')
                with tracer.start_as_current_span(span_name_, attributes=attributes, start_time=start_time):
                    self._span_start(tracer, start_parent_id, start_time, msg_template or span_name_, *kwarg_groups)
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    # Logging
    def log(self, msg_template: LiteralString, level: LevelName, kwargs: Any) -> None:
        msg = logfire_format(msg_template, kwargs)
        tracer = self._get_context_tracer()
        start_time = int(time.time() * 1e9)  # OpenTelemetry uses ns for timestamps

        user_attributes = self._user_attributes(kwargs)
        logfire_attributes = self._logfire_attributes('log', msg_template=msg_template, level=level)
        attributes = {**user_attributes, **logfire_attributes}

        span = tracer.start_span(name=msg, start_time=start_time, attributes=attributes)
        span.end(start_time)
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
        span_id = trace.get_current_span(None).get_span_context().span_id
        if span_id == 0:
            return None
        return format_span_id(span_id)

    def _span_start(
        self,
        tracer: Tracer,
        outer_parent_id: str | None,
        start_time: int,
        msg_template: str,
        *kwarg_groups: dict[str, Any],
    ) -> Span:
        """Send a zero length span at the start of the main span to represent the span opening.

        This is required since the span itself isn't sent until it's closed.
        """
        msg = logfire_format(msg_template, *kwarg_groups)

        logfire_attributes = self._logfire_attributes(
            'start_span', msg_template=msg_template, start_parent_id=outer_parent_id
        )
        user_attributes: dict[str, AttributeValue] = {}
        for kw in kwarg_groups:
            if kw:
                user_attributes.update(self._user_attributes(kw))
        attributes = {**logfire_attributes, **user_attributes}

        start_span = tracer.start_span(name=msg, start_time=start_time, attributes=attributes)
        start_span.end(start_time)
        with trace.use_span(start_span):
            pass

        return start_span

    def _get_context_tracer(self) -> Tracer:
        tracer = self._tracer.get()
        if tracer is None:
            return self._get_tracer(self._config.service_name)
        return tracer

    def _get_tracer(self, name: str) -> Tracer:
        # NOTE(David): Should we add version, schema_url?
        return trace.get_tracer(name, tracer_provider=self._telemetry.provider)

    def _logfire_attributes(
        self,
        log_type: LogTypeType,
        *,
        msg_template: str | None = None,
        level: LevelName | None = None,
        start_parent_id: str | None = None,
    ) -> dict[str, AttributeValue]:
        tags = self._get_tags()
        return _dict_not_none(
            **{
                LOG_TYPE_KEY: log_type,
                LEVEL_KEY: level,
                MSG_TEMPLATE_KEY: msg_template,
                TAGS_KEY: tags,
                START_PARENT_ID: start_parent_id,
            }
        )

    def _user_attributes(self, attributes: dict[str, Any]) -> dict[str, AttributeValue]:
        """Prepare attributes for sending to OpenTelemetry.

        This will convert any non-OpenTelemetry compatible types to JSON.
        """
        prepared: dict[str, AttributeValue] = {}

        for k, v in attributes.items():
            self._set_user_attribute(prepared, k, v, '')

        return prepared

    def _set_user_attribute(
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
        else:
            dumped_value = _ANY_TYPE_ADAPTER.dump_json(value)
            target[prefixed_key + NON_SCALAR_VAR_SUFFIX] = dumped_value

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
