"""Backfill logfire logs and spans from a file or stream."""

from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Dict, Union

from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import SpanContext, SpanKind, TraceFlags
from opentelemetry.trace.status import Status, StatusCode

from .constants import (
    ATTRIBUTES_LOG_LEVEL_NUM_KEY,
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    LEVEL_NUMBERS,
    LevelName,
)
from .exporters.file import FileSpanExporter
from .formatter import logfire_format
from .main import user_attributes
from .scrubbing import Scrubber

try:
    from pydantic import BaseModel, ConfigDict, Field
except ImportError as e:  # pragma: no cover
    raise ImportError('Pydantic is required to use `logfire.import`, run `pip install pydantic`.') from e


__all__ = 'generate_trace_id', 'generate_span_id', 'Log', 'StartSpan', 'PrepareBackfill'
_ID_GENERATOR = RandomIdGenerator()


def generate_trace_id() -> int:  # pragma: no cover
    """Generate a new trace ID.

    Returns:
        A new trace ID.
    """
    return _ID_GENERATOR.generate_trace_id()


def generate_span_id() -> int:  # pragma: no cover
    """Generate a new span ID.

    Returns:
        A new span ID.
    """
    return _ID_GENERATOR.generate_span_id()


pydantic_config = ConfigDict(plugin_settings={'logfire': {'record': 'off'}})


class Log(BaseModel):
    """A log record."""

    model_config = pydantic_config
    msg_template: str
    level: LevelName
    service_name: str
    attributes: Dict[str, Any]
    trace_id: int = Field(default_factory=generate_trace_id)
    span_id: int = Field(default_factory=generate_span_id)
    parent_span_id: Union[int, None] = None
    timestamp: Union[datetime, None] = None
    formatted_msg: Union[str, None] = None
    otel_resource_attributes: Dict[str, Any] = Field(default_factory=dict)


class StartSpan(BaseModel):
    """A span."""

    model_config = pydantic_config
    span_name: str
    msg_template: str
    service_name: str
    parent: Union['StartSpan', int, None] = None
    """The parent span or span ID."""
    log_attributes: Dict[str, Any]
    span_id: int = Field(default_factory=generate_span_id)
    trace_id: int = Field(default_factory=generate_trace_id)
    parent_span_id: Union[int, None] = None
    start_timestamp: Union[datetime, None] = None
    formatted_msg: Union[str, None] = None
    otel_resource_attributes: Dict[str, Any] = Field(default_factory=dict)

    def end(self, end_timestamp: datetime) -> 'Span':
        """End the span at a given timestamp."""
        return Span.model_construct(
            span_name=self.span_name,
            msg_template=self.msg_template,
            service_name=self.service_name,
            log_attributes=self.log_attributes,
            span_id=self.span_id,
            trace_id=self.trace_id,
            parent_span_id=self.parent_span_id,
            start_timestamp=self.start_timestamp,
            end_timestamp=end_timestamp,
            formatted_msg=self.formatted_msg,
            otel_resource_attributes=self.otel_resource_attributes,
        )


class Span(StartSpan):
    end_timestamp: Union[datetime, None] = None


class PrepareBackfill:
    """Prepare a backfill of logfire logs and spans from a file or stream.

    Attributes:
        store_path: The path to the file or stream to backfill.
        open_spans: A mapping of open spans, keyed by (trace_id, span_id).
        processor: The span processor to use for the backfill.
    """

    def __init__(self, file: Union[Path, str, IO[bytes]], batch: bool = True) -> None:
        self.store_path = Path(file) if isinstance(file, str) else file
        if batch:
            self.processor = BatchSpanProcessor(
                span_exporter=FileSpanExporter(self.store_path),
            )
        else:
            self.processor = SimpleSpanProcessor(FileSpanExporter(self.store_path))
        self.scrubber = Scrubber([])

    def __enter__(self) -> 'PrepareBackfill':
        return self

    def write(self, data: Union[Log, Span]) -> None:
        """Write the data to the backfill."""
        # convert the span to an otel span
        if isinstance(data, Log):
            timestamp = data.timestamp or datetime.now(tz=timezone.utc)
            if timestamp.tzinfo is None:  # pragma: no branch
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            timestamp = int(timestamp.timestamp() * 1e9)
            if data.parent_span_id is not None:
                parent_context = SpanContext(
                    trace_id=data.trace_id,
                    span_id=data.parent_span_id,
                    is_remote=False,
                )
            else:
                parent_context = None  # pragma: no cover
            otlp_attributes = user_attributes(data.attributes)

            if data.formatted_msg is None:  # pragma: no cover
                formatted_message = logfire_format(data.msg_template, data.attributes, self.scrubber)
            else:
                formatted_message = data.formatted_msg
            otlp_attributes: dict[str, Any] = {
                ATTRIBUTES_SPAN_TYPE_KEY: 'log',
                ATTRIBUTES_LOG_LEVEL_NUM_KEY: LEVEL_NUMBERS[data.level],
                ATTRIBUTES_MESSAGE_TEMPLATE_KEY: data.msg_template,
                ATTRIBUTES_MESSAGE_KEY: formatted_message,
                **otlp_attributes,
            }
            span = ReadableSpan(
                name=data.msg_template,
                context=SpanContext(
                    trace_id=data.trace_id,
                    span_id=data.span_id,
                    is_remote=False,
                    trace_flags=TraceFlags(TraceFlags.SAMPLED),
                ),
                parent=parent_context,
                resource=Resource.create(
                    {ResourceAttributes.SERVICE_NAME: data.service_name, **data.otel_resource_attributes}
                ),
                instrumentation_scope=InstrumentationScope(
                    name='logfire',
                ),
                attributes=BoundedAttributes(attributes=otlp_attributes),
                events=[],
                links=[],
                kind=SpanKind.INTERNAL,
                start_time=timestamp,
                end_time=timestamp,
                status=Status(StatusCode.OK),
            )
        else:  # always a Span
            assert isinstance(data, Span)
            assert data.start_timestamp is not None
            assert data.end_timestamp is not None
            end_timestamp = data.end_timestamp or datetime.now(tz=timezone.utc)
            if end_timestamp.tzinfo is None:  # pragma: no branch
                end_timestamp = end_timestamp.replace(tzinfo=timezone.utc)
            start_timestamp = data.start_timestamp
            if start_timestamp.tzinfo is None:  # pragma: no branch
                start_timestamp = start_timestamp.replace(tzinfo=timezone.utc)
            otlp_attributes = user_attributes(data.log_attributes)
            if data.formatted_msg is None:  # pragma: no branch
                formatted_message = logfire_format(data.msg_template, data.log_attributes, self.scrubber)
            else:  # pragma: no cover
                formatted_message = data.formatted_msg
            otlp_attributes: dict[str, Any] = {
                ATTRIBUTES_SPAN_TYPE_KEY: 'log',
                ATTRIBUTES_MESSAGE_TEMPLATE_KEY: data.msg_template,
                ATTRIBUTES_MESSAGE_KEY: formatted_message,
                **otlp_attributes,
            }
            span = ReadableSpan(
                name=data.span_name,
                context=SpanContext(
                    trace_id=data.trace_id,
                    span_id=data.span_id,
                    is_remote=False,
                    trace_flags=TraceFlags(TraceFlags.SAMPLED),
                ),
                parent=None,
                resource=Resource.create(
                    {ResourceAttributes.SERVICE_NAME: data.service_name, **data.otel_resource_attributes}
                ),
                instrumentation_scope=InstrumentationScope(
                    name='logfire',
                ),
                attributes=BoundedAttributes(attributes=otlp_attributes),
                events=[],
                links=[],
                kind=SpanKind.INTERNAL,
                start_time=int(start_timestamp.timestamp() * 1e9),
                end_time=int(end_timestamp.timestamp() * 1e9),
                status=Status(StatusCode.OK),
            )

        self.processor.on_end(span)

    def __exit__(self, *_: Any) -> None:
        self.processor.force_flush()
        self.processor.shutdown()
