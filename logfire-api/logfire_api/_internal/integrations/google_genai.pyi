import logfire
from logfire._internal.utils import handle_internal_errors as handle_internal_errors
from opentelemetry._events import Event, EventLogger, EventLoggerProvider
from typing import Any

class SpanEventLogger(EventLogger):
    @handle_internal_errors
    def emit(self, event: Event) -> None: ...

class SpanEventLoggerProvider(EventLoggerProvider):
    def get_event_logger(self, *args: Any, **kwargs: Any) -> SpanEventLogger: ...

def instrument_google_genai(logfire_instance: logfire.Logfire): ...
