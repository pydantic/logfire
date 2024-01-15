from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from threading import Lock
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Sequence,
    cast,
)
from weakref import WeakKeyDictionary

import opentelemetry.trace as trace_api
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, Tracer as SDKTracer, TracerProvider as SDKTracerProvider
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import Link, Span, SpanContext, SpanKind, Tracer, TracerProvider
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util import types as otel_types

from ._constants import (
    ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY,
    ATTRIBUTES_SAMPLE_RATE_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    PENDING_SPAN_NAME_SUFFIX,
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

    def set_provider(self, provider: SDKTracerProvider) -> None:
        with self.lock:
            self.provider = provider
            for tracer, factory in self.tracers.items():
                tracer.set_tracer(factory())

    def get_tracer(
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: str | None = None,
        schema_url: str | None = None,
        is_span_tracer: bool = True,
    ) -> _ProxyTracer:
        with self.lock:

            def make() -> Tracer:
                return self.provider.get_tracer(
                    instrumenting_module_name=instrumenting_module_name,
                    instrumenting_library_version=instrumenting_library_version,
                    schema_url=schema_url,
                )

            tracer = _ProxyTracer(make(), self, is_span_tracer)
            self.tracers[tracer] = make
            return tracer

    def add_span_processor(self, span_processor: Any) -> None:
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
            return Resource.create({ResourceAttributes.SERVICE_NAME: self.config.service_name})

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
class _ProxyTracer(Tracer):
    """A tracer that wraps another internal tracer allowing it to be re-assigned."""

    tracer: Tracer
    provider: ProxyTracerProvider
    is_span_tracer: bool

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: object) -> bool:
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
        start_time = start_time or self.provider.config.ns_timestamp_generator()
        attributes = attributes or {}
        if self.is_span_tracer:
            attributes = {**attributes, ATTRIBUTES_SPAN_TYPE_KEY: 'span'}
        span = self.tracer.start_span(
            name, context, kind, attributes, links, start_time, record_exception, set_status_on_exception
        )
        sample_rate = get_sample_rate_from_attributes(attributes)
        if sample_rate is not None and not should_sample(span.get_span_context().span_id, sample_rate):
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
        elif self.is_span_tracer and span.is_recording():
            assert isinstance(span, ReadableSpan)  # in practice always true since we are wrapping a real tracer
            # this pending span may never be used but we send it anyway since we can just ignore it if it is not used
            _emit_pending_span(
                tracer=self.tracer,
                name=name,
                start_time=start_time or self.provider.config.ns_timestamp_generator(),
                attributes=attributes,
                real_span=span,
            )
        return _MaybeDeterministicTimestampSpan(
            span,
            ns_timestamp_generator=self.provider.config.ns_timestamp_generator,
        )

    # This means that `with start_as_current_span(...):`
    # is roughly equivalent to `with use_span(start_span(...)):`
    start_as_current_span = SDKTracer.start_as_current_span  # type: ignore


OK_STATUS = trace_api.Status(trace_api.StatusCode.OK)


def _emit_pending_span(
    *,
    tracer: Tracer,
    name: str,
    start_time: int,
    attributes: Mapping[str, otel_types.AttributeValue],
    real_span: ReadableSpan,
) -> None:
    """Emit a pending span.

    Pending spans send metadata about a span before it completes so that our UI can
    display it.
    """
    attributes = {
        **attributes,
        ATTRIBUTES_SPAN_TYPE_KEY: 'pending_span',
        # use str here since protobuf can't encode ints above 2^64,
        # see https://github.com/pydantic/platform/pull/388
        ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY: trace_api.format_span_id(
            real_span.parent.span_id if real_span.parent else 0
        ),
    }
    real_span_context = real_span.get_span_context()
    if real_span_context:
        span_context = real_span_context
    else:
        span_context = SpanContext(
            trace_id=trace_api.INVALID_TRACE_ID,
            span_id=trace_api.INVALID_SPAN_ID,
            is_remote=False,
            trace_flags=trace_api.TraceFlags(trace_api.TraceFlags.DEFAULT),
        )

    ctx = trace_api.set_span_in_context(trace_api.NonRecordingSpan(span_context))
    pending_span = tracer.start_span(
        name + PENDING_SPAN_NAME_SUFFIX,  # avoid confusing other implementations with duplicate span names
        attributes=attributes,
        start_time=start_time,
        context=ctx,
    )
    pending_span.set_status(OK_STATUS)
    pending_span.end(start_time)


def should_sample(span_id: int, sample_rate: float) -> bool:
    """Determine if a span should be sampled.

    This is used to sample spans that are not sampled by the OTEL sampler.
    """
    return span_id <= round(sample_rate * 2**64)


def get_sample_rate_from_attributes(attributes: otel_types.Attributes) -> float | None:
    if not attributes:
        return None
    return cast('float | None', attributes.get(ATTRIBUTES_SAMPLE_RATE_KEY))
