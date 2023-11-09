from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterator,
    Sequence,
)
from weakref import WeakKeyDictionary, WeakSet

import opentelemetry.trace as trace_api
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider as SDKTracerProvider
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import Link, Span, SpanContext, SpanKind, Tracer, TracerProvider, use_span
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util import types as otel_types

from ._constants import (
    ATTRIBUTES_SPAN_TYPE_KEY,
    ATTRIBUTES_START_SPAN_REAL_PARENT_KEY,
    START_SPAN_NAME_SUFFIX,
)

if TYPE_CHECKING:
    from logfire._config import LogfireConfig


@dataclass
class ProxyTracerProvider(TracerProvider):
    """A tracer provider that wraps another internal tracer provider allowing it to be re-assigned."""

    provider: TracerProvider
    config: LogfireConfig
    tracers: WeakKeyDictionary[_ProxyTracer, Callable[[], Tracer]] = field(default_factory=WeakKeyDictionary)
    lock: Lock = field(default_factory=Lock)
    # this list of span_processors is not actually used directly, we just keep track of them for our own testing purposes
    span_processors: WeakSet[SpanProcessor] = field(default_factory=WeakSet)

    def set_provider(self, provider: SDKTracerProvider) -> None:
        self.span_processors.clear()
        with self.lock:
            self.provider = provider
            for tracer, factory in self.tracers.items():
                tracer.set_tracer(factory())

    def get_tracer(
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: str | None = None,
        schema_url: str | None = None,
        wrap_with_start_span_tracer: bool = True,
    ) -> _ProxyTracer:
        with self.lock:

            def make() -> Tracer:
                tracer = self.provider.get_tracer(
                    instrumenting_module_name=instrumenting_module_name,
                    instrumenting_library_version=instrumenting_library_version,
                    schema_url=schema_url,
                )
                if wrap_with_start_span_tracer:
                    tracer = _StartSpanTracer(tracer, self)
                return tracer

            tracer = _ProxyTracer(make(), self)
            self.tracers[tracer] = make
            return tracer

    def add_span_processor(self, span_processor: Any) -> None:
        self.span_processors.add(span_processor)
        with self.lock:
            if isinstance(self.provider, SDKTracerProvider):
                self.provider.add_span_processor(span_processor)

    def shutdown(self) -> None:
        with self.lock:
            if isinstance(self.provider, SDKTracerProvider):
                self.provider.shutdown()

    @property
    def resource(self) -> Resource:
        with self.lock:
            if isinstance(self.provider, SDKTracerProvider):
                return self.provider.resource
            return Resource.create({ResourceAttributes.SERVICE_NAME: 'unknown'})

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        with self.lock:
            if isinstance(self.provider, SDKTracerProvider):
                return self.provider.force_flush(timeout_millis)
            return True


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

    def add_event(
        self,
        name: str,
        attributes: otel_types.Attributes = None,
        timestamp: int | None = None,
    ) -> None:
        self.span.add_event(name, attributes, timestamp)

    def update_name(self, name: str) -> None:
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
        exception: Exception,
        attributes: otel_types.Attributes = None,
        timestamp: int | None = None,
        escaped: bool = False,
    ) -> None:
        timestamp = timestamp or self.ns_timestamp_generator()
        return self.span.record_exception(exception, attributes, timestamp, escaped)

    if not TYPE_CHECKING:
        # for ReadableSpan
        def __getattr__(self, name: str) -> Any:
            return getattr(self.span, name)


@dataclass
class _StartSpanTracer(trace_api.Tracer):
    """A tracer that emits start spans.

    This is used to make non-logfire OTEL libraries emit start spans.
    """

    tracer: Tracer
    provider: ProxyTracerProvider

    @contextmanager
    def start_as_current_span(
        self,
        name: str,
        context: Context | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: otel_types.Attributes = None,
        links: Sequence[Link] | None = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
        end_on_exit: bool = True,
    ) -> Iterator[Span]:
        span = _MaybeDeterministicTimestampSpan(
            self.tracer.start_span(
                name,
                context=context,
                kind=kind,
                attributes={**(attributes or {}), ATTRIBUTES_SPAN_TYPE_KEY: 'span'},
                links=links or (),
                start_time=start_time,
                record_exception=record_exception,
                set_status_on_exception=set_status_on_exception,
            ),
            ns_timestamp_generator=self.provider.config.ns_timestamp_generator,
        )
        with trace_api.use_span(span, end_on_exit=end_on_exit, record_exception=record_exception):
            _emit_start_span(
                tracer=self.tracer,
                name=name,
                start_time=start_time or self.provider.config.ns_timestamp_generator(),
                attributes=attributes,
                real_span=span,
            )
            yield span

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
        span = self.tracer.start_span(
            name,
            context,
            kind,
            {**(attributes or {}), ATTRIBUTES_SPAN_TYPE_KEY: 'span'},
            links,
            start_time,
            record_exception,
            set_status_on_exception,
        )
        if span.is_recording():
            assert isinstance(span, ReadableSpan)  # in practice always true since we are wrapping a real tracer
            # this start span may never be used but we send it anyway since we can just ignore it if it is not used
            _emit_start_span(
                tracer=self.tracer,
                name=name,
                start_time=start_time or self.provider.config.ns_timestamp_generator(),
                attributes=attributes,
                real_span=span,
            )
        return span


@dataclass
class _ProxyTracer(Tracer):
    """A tracer that wraps another internal tracer allowing it to be re-assigned."""

    tracer: Tracer
    provider: ProxyTracerProvider

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: object) -> bool:
        return other is self

    def set_tracer(self, tracer: Tracer) -> None:
        self.tracer = tracer

    @contextmanager
    def start_as_current_span(
        self,
        name: str,
        context: Context | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: otel_types.Attributes = None,
        links: Sequence[Link] | None = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
        end_on_exit: bool = True,
    ) -> Iterator[Span]:
        start_time = start_time or self.provider.config.ns_timestamp_generator()
        with self.tracer.start_as_current_span(
            name,
            context=context,
            kind=kind,
            attributes=attributes,
            links=links or (),
            start_time=start_time,
            record_exception=record_exception,
            set_status_on_exception=set_status_on_exception,
            end_on_exit=end_on_exit,
        ) as span:
            yield _MaybeDeterministicTimestampSpan(
                span, ns_timestamp_generator=self.provider.config.ns_timestamp_generator
            )

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
        start_time = start_time or self.provider.config.ns_timestamp_generator()
        return _MaybeDeterministicTimestampSpan(
            self.tracer.start_span(
                name, context, kind, attributes, links, start_time, record_exception, set_status_on_exception
            ),
            ns_timestamp_generator=self.provider.config.ns_timestamp_generator,
        )


def _emit_start_span(
    *,
    tracer: Tracer,
    name: str,
    start_time: int,
    attributes: otel_types.Attributes,
    real_span: ReadableSpan,
) -> Span:
    """Emit a start span.

    Start spans send metadata about a span before it completes so that our UI can
    display it.
    """
    attributes = dict(attributes) if attributes else {}
    real_span_context = real_span.get_span_context()
    attributes.update(
        {
            ATTRIBUTES_SPAN_TYPE_KEY: 'start_span',
            # use str here since protobuf can't encode ints above 2^64,
            # see https://github.com/pydantic/platform/pull/388
            ATTRIBUTES_START_SPAN_REAL_PARENT_KEY: str(real_span.parent.span_id if real_span.parent else 0),
        }
    )
    span_context = SpanContext(
        trace_id=real_span_context.trace_id,
        span_id=real_span_context.span_id,
        is_remote=False,
        trace_flags=real_span_context.trace_flags,
    )
    ctx = trace_api.set_span_in_context(trace_api.NonRecordingSpan(span_context))
    start_span = tracer.start_span(
        name + START_SPAN_NAME_SUFFIX,  # avoid confusing other implementations with duplicate span names
        attributes=attributes,
        start_time=start_time,
        context=ctx,
    )
    with use_span(start_span, end_on_exit=False):
        start_span.set_status(trace_api.Status(trace_api.StatusCode.OK))
        start_span.end(start_time)
    return start_span
