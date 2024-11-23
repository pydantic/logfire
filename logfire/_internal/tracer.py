from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence, cast
from weakref import WeakKeyDictionary

import opentelemetry.trace as trace_api
from opentelemetry import context as context_api
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import (
    ReadableSpan,
    SpanProcessor,
    Tracer as SDKTracer,
    TracerProvider as SDKTracerProvider,
)
from opentelemetry.sdk.trace.id_generator import IdGenerator
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import Link, Span, SpanContext, SpanKind, Tracer, TracerProvider
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util import types as otel_types

from .constants import (
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY,
    ATTRIBUTES_SAMPLE_RATE_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    PENDING_SPAN_NAME_SUFFIX,
)

if TYPE_CHECKING:
    from .config import LogfireConfig


@dataclass
class ProxyTracerProvider(TracerProvider):
    """A tracer provider that wraps another internal tracer provider allowing it to be re-assigned."""

    provider: TracerProvider
    config: LogfireConfig
    tracers: WeakKeyDictionary[_ProxyTracer, Callable[[], Tracer]] = field(default_factory=WeakKeyDictionary)
    lock: Lock = field(default_factory=Lock)

    def set_provider(self, provider: SDKTracerProvider) -> None:
        with self.lock:
            self.provider = provider
            for tracer, factory in self.tracers.items():
                tracer.set_tracer(factory())

    def get_tracer(
        self,
        *args: Any,
        is_span_tracer: bool = True,
        **kwargs: Any,
    ) -> _ProxyTracer:
        with self.lock:

            def make() -> Tracer:
                return self.provider.get_tracer(*args, **kwargs)

            tracer = _ProxyTracer(make(), self, is_span_tracer)
            self.tracers[tracer] = make
            return tracer

    def add_span_processor(self, span_processor: Any) -> None:  # pragma: no cover
        with self.lock:
            if isinstance(self.provider, SDKTracerProvider):
                self.provider.add_span_processor(span_processor)

    def shutdown(self) -> None:
        with self.lock:
            if isinstance(self.provider, SDKTracerProvider):
                self.provider.shutdown()

    @property
    def resource(self) -> Resource:  # pragma: no cover
        with self.lock:
            if isinstance(self.provider, SDKTracerProvider):
                return self.provider.resource
            return Resource.create({ResourceAttributes.SERVICE_NAME: self.config.service_name})

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        with self.lock:
            if isinstance(self.provider, SDKTracerProvider):  # pragma: no branch
                return self.provider.force_flush(timeout_millis)
            return True  # pragma: no cover


@dataclass
class _MaybeDeterministicTimestampSpan(trace_api.Span, ReadableSpan):
    """Span that overrides end() to use a timestamp generator if one was provided."""

    span: Span
    ns_timestamp_generator: Callable[[], int]

    def end(self, end_time: int | None = None) -> None:
        self.span.end(end_time or self.ns_timestamp_generator())

    def get_span_context(self) -> SpanContext:
        return self.span.get_span_context()

    def set_attributes(self, attributes: dict[str, otel_types.AttributeValue]) -> None:
        self.span.set_attributes(attributes)

    def set_attribute(self, key: str, value: otel_types.AttributeValue) -> None:
        self.span.set_attribute(key, value)

    def add_link(self, context: SpanContext, attributes: otel_types.Attributes = None) -> None:
        return self.span.add_link(context, attributes)

    def add_event(
        self,
        name: str,
        attributes: otel_types.Attributes = None,
        timestamp: int | None = None,
    ) -> None:
        self.span.add_event(name, attributes, timestamp or self.ns_timestamp_generator())

    def update_name(self, name: str) -> None:  # pragma: no cover
        self.span.update_name(name)

    def is_recording(self) -> bool:
        return self.span.is_recording()

    def set_status(
        self,
        status: Status | StatusCode,
        description: str | None = None,
    ) -> None:
        self.span.set_status(status, description)

    def record_exception(
        self,
        exception: BaseException,
        attributes: otel_types.Attributes = None,
        timestamp: int | None = None,
        escaped: bool = False,
    ) -> None:
        timestamp = timestamp or self.ns_timestamp_generator()
        return self.span.record_exception(exception, attributes, timestamp, escaped)

    if not TYPE_CHECKING:  # pragma: no branch
        # for ReadableSpan
        def __getattr__(self, name: str) -> Any:
            return getattr(self.span, name)


@dataclass
class _ProxyTracer(Tracer):
    """A tracer that wraps another internal tracer allowing it to be re-assigned."""

    tracer: Tracer
    provider: ProxyTracerProvider
    is_span_tracer: bool

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: object) -> bool:  # pragma: no cover
        return other is self

    def set_tracer(self, tracer: Tracer) -> None:
        self.tracer = tracer

    def start_span(
        self,
        name: str,
        context: Context | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: otel_types.Attributes = None,
        links: Sequence[Link] | None = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ) -> Span:
        start_time = start_time or self.provider.config.advanced.ns_timestamp_generator()

        # Make a copy of the attributes since this method can be called by arbitrary external code,
        # e.g. third party instrumentation.
        attributes = {**(attributes or {})}
        if self.is_span_tracer:
            attributes[ATTRIBUTES_SPAN_TYPE_KEY] = 'span'
        attributes.setdefault(ATTRIBUTES_MESSAGE_KEY, name)

        span = self.tracer.start_span(
            name, context, kind, attributes, links, start_time, record_exception, set_status_on_exception
        )
        if not should_sample(span.get_span_context(), attributes):  # pragma: no cover
            span = trace_api.NonRecordingSpan(
                SpanContext(
                    trace_id=span.get_span_context().trace_id,
                    span_id=span.get_span_context().span_id,
                    is_remote=False,
                    trace_flags=trace_api.TraceFlags(
                        span.get_span_context().trace_flags & ~trace_api.TraceFlags.SAMPLED
                    ),
                )
            )
        return _MaybeDeterministicTimestampSpan(
            span,
            ns_timestamp_generator=self.provider.config.advanced.ns_timestamp_generator,
        )

    # This means that `with start_as_current_span(...):`
    # is roughly equivalent to `with use_span(start_span(...)):`
    start_as_current_span = SDKTracer.start_as_current_span


@dataclass
class PendingSpanProcessor(SpanProcessor):
    """Span processor that emits an extra pending span for each span as it starts.

    The pending span is emitted by calling `on_end` on all other processors.
    """

    id_generator: IdGenerator
    other_processors: tuple[SpanProcessor, ...]

    def on_start(
        self,
        span: Span,
        parent_context: context_api.Context | None = None,
    ) -> None:
        assert isinstance(span, ReadableSpan) and isinstance(span, Span)
        if not span.is_recording():  # pragma: no cover
            # Span was sampled out
            return

        attributes = span.attributes
        if not attributes or attributes.get(ATTRIBUTES_SPAN_TYPE_KEY) == 'log':
            return

        real_span_context = span.get_span_context()
        if not should_sample(real_span_context, attributes):  # pragma: no cover
            # Currently our own sampling is only checked after the span has started,
            # so we have to repeat that check here.
            # This might change in the future, see
            # https://linear.app/pydantic/issue/PYD-552/sampling-behaves-very-differently-depending-on-how-its-configured
            return

        span_context = SpanContext(
            trace_id=real_span_context.trace_id,
            span_id=self.id_generator.generate_span_id(),
            is_remote=False,
            trace_flags=real_span_context.trace_flags,
        )
        attributes = {
            **attributes,
            ATTRIBUTES_SPAN_TYPE_KEY: 'pending_span',
            # use str here since protobuf can't encode ints above 2^64,
            # see https://github.com/pydantic/platform/pull/388
            ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY: trace_api.format_span_id(
                span.parent.span_id if span.parent else 0
            ),
        }
        start_and_end_time = span.start_time
        pending_span = ReadableSpan(
            name=span.name + PENDING_SPAN_NAME_SUFFIX,
            context=span_context,
            parent=real_span_context,
            resource=span.resource,
            attributes=attributes,
            events=span.events,
            links=span.links,
            status=span.status,
            kind=span.kind,
            start_time=start_and_end_time,
            end_time=start_and_end_time,
            instrumentation_scope=span.instrumentation_scope,
        )
        for processor in self.other_processors:
            processor.on_end(pending_span)


def should_sample(span_context: SpanContext, attributes: Mapping[str, otel_types.AttributeValue]) -> bool:
    """Determine if a span should be sampled.

    This is used to sample spans that are not sampled by the OTEL sampler.
    """
    sample_rate = get_sample_rate_from_attributes(attributes)
    return sample_rate is None or span_context.span_id <= round(sample_rate * 2**64)


def get_sample_rate_from_attributes(attributes: otel_types.Attributes) -> float | None:
    if not attributes:  # pragma: no cover
        return None
    return cast('float | None', attributes.get(ATTRIBUTES_SAMPLE_RATE_KEY))
