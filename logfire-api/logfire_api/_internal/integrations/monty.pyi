from collections.abc import Sequence
from logfire import Logfire as Logfire
from opentelemetry._logs import Logger, LogRecord
from opentelemetry.context import Context
from opentelemetry.trace import Link, Span, SpanKind, Tracer
from opentelemetry.util import types as otel_types
from typing import Any

def instrument_monty(logfire_instance: Logfire) -> None: ...

class LogfireMontyTracer(Tracer):
    logfire: Logfire
    def __init__(self, logfire_instance: Logfire) -> None: ...
    def start_span(self, name: str, context: Context | None = None, kind: SpanKind = SpanKind.INTERNAL, attributes: otel_types.Attributes = None, links: Sequence[Link] | None = None, start_time: int | None = None, record_exception: bool = True, set_status_on_exception: bool = True) -> Span: ...
    start_as_current_span: Any

class LogfireMontyLogger(Logger):
    logger: Logger
    logfire: Logfire
    def __init__(self, logger: Logger, logfire_instance: Logfire) -> None: ...
    def emit(self, record: LogRecord | None = None, **kwargs: Any) -> None: ...
