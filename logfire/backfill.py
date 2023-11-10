"""Backfill logfire logs and spans from a file or stream."""
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Dict, Literal, Union

from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator
from opentelemetry.sdk.util.instrumentation import (
    InstrumentationScope,
)
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import SpanContext, SpanKind, TraceFlags
from opentelemetry.trace.status import Status, StatusCode
from typing_extensions import Annotated, Self

from ._constants import (
    ATTRIBUTES_LOG_LEVEL_KEY,
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    LevelName,
)
from ._formatter import logfire_format
from ._main import user_attributes
from .exporters._file import FileSpanExporter

try:
    from pydantic import BaseModel, ConfigDict, Field, validate_call
except ImportError as e:
    raise ImportError('pydantic is required to use logfire.import, run `pip install logfire[backfill]`') from e


__all__ = 'generate_trace_id', 'generate_span_id', 'RecordLog', 'StartSpan', 'EndSpan', 'PrepareBackfill'
ID_GENERATOR = RandomIdGenerator()


def generate_trace_id() -> int:
    """Generate a new trace ID.

    Returns:
        A new trace ID.
    """
    return ID_GENERATOR.generate_trace_id()


def generate_span_id() -> int:
    """Generate a new span ID.

    Returns:
        A new span ID.
    """
    return ID_GENERATOR.generate_span_id()


pydantic_config = ConfigDict(plugin_settings={'logfire': {'record': 'off'}})


class RecordLog(BaseModel):
    """A log record."""

    model_config = pydantic_config
    type: Literal['log'] = 'log'
    msg_template: str
    level: LevelName
    service_name: str
    attributes: Dict[str, Any]
    trace_id: int = Field(default_factory=generate_trace_id)
    span_id: int = Field(default_factory=generate_span_id)
    parent_span_id: Union[int, None] = None
    timestamp: Union[datetime, None] = None
    formatted_msg: Union[str, None] = None
    resource_attributes: Dict[str, Any] = Field(default_factory=dict)


class StartSpan(BaseModel):
    """The start of a span."""

    model_config = pydantic_config
    type: Literal['start_span'] = 'start_span'
    span_name: str
    msg_template: str
    service_name: str
    log_attributes: Dict[str, Any]
    span_id: int = Field(default_factory=generate_span_id)
    trace_id: int = Field(default_factory=generate_trace_id)
    parent_span_id: Union[int, None] = None
    start_timestamp: Union[datetime, None] = None
    formatted_msg: Union[str, None] = None
    resource_attributes: Dict[str, Any] = Field(default_factory=dict)


class EndSpan(BaseModel):
    """The end of a span."""

    model_config = pydantic_config
    type: Literal['end_span'] = 'end_span'
    span_id: int
    trace_id: int
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
        self.open_spans: dict[tuple[int, int], StartSpan] = {}
        if batch:
            self.processor = BatchSpanProcessor(
                span_exporter=FileSpanExporter(self.store_path),
            )
        else:
            self.processor = SimpleSpanProcessor(FileSpanExporter(self.store_path))

    def __enter__(self) -> Self:
        return self

    @validate_call(config=pydantic_config)
    def write(self, data: Annotated[Union[RecordLog, StartSpan, EndSpan], Field(discriminator='type')]) -> None:
        """Write the data to the backfill."""
        if isinstance(data, StartSpan):
            key = (data.trace_id, data.span_id)
            assert key not in self.open_spans, f'start span ID {data.span_id} found in open spans'
            data.start_timestamp = data.start_timestamp or datetime.now(tz=timezone.utc)
            self.open_spans[key] = data
            return
        # convert the span to an otel span
        if isinstance(data, RecordLog):
            timestamp = data.timestamp or datetime.now(tz=timezone.utc)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            timestamp = int(timestamp.timestamp() * 1e9)
            if data.parent_span_id is not None:
                parent_context = SpanContext(
                    trace_id=data.trace_id,
                    span_id=data.parent_span_id,
                    is_remote=False,
                )
            else:
                parent_context = None
            otlp_attributes = user_attributes(data.attributes)

            if data.formatted_msg is None:
                formatted_message = logfire_format(data.msg_template, data.attributes, fallback='...', stacklevel=2)
            else:
                formatted_message = data.formatted_msg
            otlp_attributes: dict[str, Any] = {
                ATTRIBUTES_SPAN_TYPE_KEY: 'log',
                ATTRIBUTES_LOG_LEVEL_KEY: data.level,
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
                    {ResourceAttributes.SERVICE_NAME: data.service_name, **data.resource_attributes}
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
        else:  # always an EndSpan
            key = (data.trace_id, data.span_id)
            assert key in self.open_spans, f'end span ID {data.span_id} not found in open spans'
            start_span = self.open_spans.pop(key)
            assert start_span.start_timestamp is not None
            end_timestamp = data.end_timestamp or datetime.now(tz=timezone.utc)
            if end_timestamp.tzinfo is None:
                end_timestamp = end_timestamp.replace(tzinfo=timezone.utc)
            start_timestamp = start_span.start_timestamp
            if start_timestamp.tzinfo is None:
                start_timestamp = start_timestamp.replace(tzinfo=timezone.utc)
            otlp_attributes = user_attributes(start_span.log_attributes)
            if start_span.formatted_msg is None:
                formatted_message = logfire_format(
                    start_span.msg_template, start_span.log_attributes, fallback='...', stacklevel=2
                )
            else:
                formatted_message = start_span.formatted_msg
            otlp_attributes: dict[str, Any] = {
                ATTRIBUTES_SPAN_TYPE_KEY: 'log',
                ATTRIBUTES_MESSAGE_TEMPLATE_KEY: start_span.msg_template,
                ATTRIBUTES_MESSAGE_KEY: formatted_message,
                **otlp_attributes,
            }
            span = ReadableSpan(
                name=start_span.span_name,
                context=SpanContext(
                    trace_id=start_span.trace_id,
                    span_id=data.span_id,
                    is_remote=False,
                    trace_flags=TraceFlags(TraceFlags.SAMPLED),
                ),
                parent=None,
                resource=Resource.create(
                    {ResourceAttributes.SERVICE_NAME: start_span.service_name, **start_span.resource_attributes}
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
        if self.open_spans:
            warnings.warn(f'closing backfill with {len(self.open_spans)} open spans')
