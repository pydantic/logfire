import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cached_property
from typing import Any, Literal, TypeVar

from opentelemetry import trace
from opentelemetry.sdk.trace import Resource, Span, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Tracer
from opentelemetry.util.types import AttributeValue
from pydantic import TypeAdapter
from pydantic_settings import BaseSettings
from typing_extensions import LiteralString

from logfire.exporters.http import HttpJsonSpanExporter

LEVEL_KEY = 'logfire.level'
MSG_TEMPLATE_KEY = 'logfire.msg_template'
IS_LOG_KEY = 'logfire.is_log'
_F = TypeVar('_F', bound=Callable[..., Any])
LevelName = Literal['debug', 'info', 'notice', 'warning', 'error', 'critical']


class ObserveConfig(BaseSettings):  # type: ignore
    model_config = {'_env_prefix': 'PYDANTIC_OBSERVE_DEFAULT_'}  # type: ignore

    service_name: str = 'logfire'
    endpoint: str = 'http://localhost:4318'
    verbose: bool = False


class _Telemetry:
    def __init__(self, config: ObserveConfig):
        self._config = config

        self.service_name = service_name = config.service_name
        self.self_log(f'Configuring telemetry for {service_name!r}...')
        self.set_exporter(HttpJsonSpanExporter(endpoint=config.endpoint))

    def set_exporter(self, exporter: SpanExporter | None = None) -> None:
        self.provider = TracerProvider(resource=Resource(attributes={'service.name': self.service_name}))
        self.self_log(f'Configured tracer provider with service.name={self.service_name!r}')
        exporter = exporter or HttpJsonSpanExporter(endpoint=self._config.endpoint)
        self.processor = BatchSpanProcessor(exporter, max_export_batch_size=1)
        self.provider.add_span_processor(self.processor)
        self.self_log(f'Configured span exporter with endpoint={self._config.endpoint!r}')

    def self_log(self, __msg: str) -> None:
        # TODO: probably want to make this more configurable/etc.
        if self._config.verbose:
            print(__msg)


class Observe:
    def __init__(self, config: ObserveConfig | None = None):
        self._tracer: ContextVar[Tracer | None] = ContextVar('_tracer', default=None)
        self._config: ObserveConfig = config or ObserveConfig()

    @cached_property
    def _telemetry(self) -> _Telemetry:
        # Use the
        return _Telemetry(self._config)

    # Configuration
    def configure(self, config: ObserveConfig | None = None, exporter: SpanExporter | None = None) -> None:
        if config is not None:
            self._config = config

        # Clear and recompute the cached property
        self.__dict__.pop('_telemetery', None)
        assert self._telemetry
        self._telemetry.set_exporter(exporter)

    # Spans
    @contextmanager
    def span(self, msg_template: LiteralString, /, **kwargs: Any) -> Iterator[Span]:
        msg = msg_template.format(**kwargs)
        tracer = self._get_context_tracer()

        s: Span
        with tracer.start_as_current_span(msg) as s:
            if kwargs:
                s.set_attributes(self._prepare_attributes(kwargs))
                s.set_attributes({MSG_TEMPLATE_KEY: msg_template})
            yield s

    def instrument(self, tracer_name: str | None = None, span_name: str | None = None) -> Callable[[_F], _F]:
        if tracer_name is None:
            tracer_name = sys._getframe(1).f_globals.get('__name__', self._config.service_name)

        tracer = self._get_tracer(tracer_name)  # type: ignore

        def decorator(func: _F) -> _F:
            nonlocal span_name
            if span_name is None:
                span_name = f'{func.__module__}.{func.__name__}'
            self._self_log(f'Instrumenting {func} with: {tracer_name=}, {span_name=}')
            return tracer.start_as_current_span(span_name)(func)

        return decorator

    # Logging
    def log(self, msg_template: LiteralString, level: LevelName, kwargs: Any) -> None:
        msg = msg_template.format(**kwargs)
        tracer = self._get_context_tracer()
        start_end_time = int(time.time() * 1e9)  # OpenTelemetry uses ns for timestamps

        attributes = self._prepare_attributes(kwargs)
        attributes[LEVEL_KEY] = level
        attributes[MSG_TEMPLATE_KEY] = msg_template
        attributes[IS_LOG_KEY] = True

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

    def _get_context_tracer(self):
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


_ANY_TYPE_ADAPTER = TypeAdapter(Any)
