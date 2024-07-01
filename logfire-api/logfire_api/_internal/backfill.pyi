from .constants import LevelName
from _typeshed import Incomplete
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel
from typing import Any, IO

__all__ = ['generate_trace_id', 'generate_span_id', 'Log', 'StartSpan', 'PrepareBackfill']

def generate_trace_id() -> int:
    """Generate a new trace ID.

    Returns:
        A new trace ID.
    """
def generate_span_id() -> int:
    """Generate a new span ID.

    Returns:
        A new span ID.
    """

class Log(BaseModel):
    """A log record."""
    model_config = pydantic_config
    msg_template: str
    level: LevelName
    service_name: str
    attributes: dict[str, Any]
    trace_id: int
    span_id: int
    parent_span_id: int | None
    timestamp: datetime | None
    formatted_msg: str | None
    otel_resource_attributes: dict[str, Any]

class StartSpan(BaseModel):
    """A span."""
    model_config = pydantic_config
    span_name: str
    msg_template: str
    service_name: str
    parent: StartSpan | int | None
    log_attributes: dict[str, Any]
    span_id: int
    trace_id: int
    parent_span_id: int | None
    start_timestamp: datetime | None
    formatted_msg: str | None
    otel_resource_attributes: dict[str, Any]
    def end(self, end_timestamp: datetime) -> Span:
        """End the span at a given timestamp."""

class Span(StartSpan):
    end_timestamp: datetime | None

class PrepareBackfill:
    """Prepare a backfill of logfire logs and spans from a file or stream.

    Attributes:
        store_path: The path to the file or stream to backfill.
        open_spans: A mapping of open spans, keyed by (trace_id, span_id).
        processor: The span processor to use for the backfill.
    """
    store_path: Incomplete
    processor: Incomplete
    scrubber: Incomplete
    def __init__(self, file: Path | str | IO[bytes], batch: bool = True) -> None: ...
    def __enter__(self) -> PrepareBackfill: ...
    def write(self, data: Log | Span) -> None:
        """Write the data to the backfill."""
    def __exit__(self, *_: Any) -> None: ...
