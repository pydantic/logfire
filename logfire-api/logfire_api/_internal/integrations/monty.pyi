from _typeshed import Incomplete
from collections.abc import Sequence
from logfire import Logfire as Logfire
from logfire._internal.constants import ATTRIBUTES_LOG_LEVEL_NUM_KEY as ATTRIBUTES_LOG_LEVEL_NUM_KEY, ATTRIBUTES_MESSAGE_KEY as ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_MESSAGE_TEMPLATE_KEY as ATTRIBUTES_MESSAGE_TEMPLATE_KEY, ATTRIBUTES_SAMPLE_RATE_KEY as ATTRIBUTES_SAMPLE_RATE_KEY, ATTRIBUTES_TAGS_KEY as ATTRIBUTES_TAGS_KEY, DISABLE_CONSOLE_KEY as DISABLE_CONSOLE_KEY
from logfire._internal.formatter import logfire_format as logfire_format
from logfire.version import VERSION as VERSION
from opentelemetry._logs import LogRecord, Logger
from opentelemetry.context import Context
from opentelemetry.trace import Link as Link, Span, SpanKind, Tracer
from opentelemetry.util import types as otel_types
from typing import Any

def instrument_monty(logfire_instance: Logfire) -> None:
    """Install process-wide Monty instrumentation using Logfire's OpenTelemetry components."""

class LogfireMontyTracer(Tracer):
    """Standard OTel tracer adding settings from a specific Logfire instance."""
    logfire: Incomplete
    def __init__(self, logfire_instance: Logfire) -> None: ...
    def start_span(self, name: str, context: Context | None = None, kind: SpanKind = ..., attributes: otel_types.Attributes = None, links: Sequence[Link] | None = None, start_time: int | None = None, record_exception: bool = True, set_status_on_exception: bool = True) -> Span: ...
    start_as_current_span: Incomplete

class LogfireMontyLogger(Logger):
    """Standard OTel logger adding settings from a specific Logfire instance."""
    logger: Incomplete
    logfire: Incomplete
    def __init__(self, logger: Logger, logfire_instance: Logfire) -> None: ...
    def emit(self, record: LogRecord | None = None, **kwargs: Any) -> None: ...
