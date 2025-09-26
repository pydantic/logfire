import logfire
from _typeshed import Incomplete
from logfire._internal.utils import handle_internal_errors as handle_internal_errors, safe_repr as safe_repr
from opentelemetry._events import Event, EventLogger, EventLoggerProvider
from typing import Any
from typing_extensions import TypeAlias

original_flatten_compound_value: Incomplete

def wrapped_flatten_compound_value(key: str, value: Any, *args: Any, **kwargs: Any): ...

Part: TypeAlias

def default_json(x: Any) -> str: ...

class SpanEventLogger(EventLogger):
    @handle_internal_errors
    def emit(self, event: Event) -> None: ...

def transform_part(part: Part) -> Part: ...

class SpanEventLoggerProvider(EventLoggerProvider):
    def get_event_logger(self, *args: Any, **kwargs: Any) -> SpanEventLogger: ...

def instrument_google_genai(logfire_instance: logfire.Logfire, **kwargs: Any): ...
