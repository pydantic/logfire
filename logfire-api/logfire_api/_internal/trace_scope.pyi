from contextvars import ContextVar
from dataclasses import dataclass
from opentelemetry.sdk.trace import ReadableSpan

__all__ = ['TRACE_SCOPE_CONTEXTVAR', 'TraceScope', 'current_trace_scope', 'enter_trace_scope', 'exit_trace_scope']

@dataclass
class TraceScope:
    """Mutable state shared by everything that runs inside one local root span."""
    feature_flag_targeting_key: str | None = ...

TRACE_SCOPE_CONTEXTVAR: ContextVar[TraceScope | None]

def current_trace_scope() -> TraceScope | None:
    """Return the scope of the local trace that the current context belongs to, if any."""
def enter_trace_scope(span: ReadableSpan) -> None:
    """Start a new scope in the current context if `span` is a local root span."""
def exit_trace_scope(span: ReadableSpan) -> None:
    """Restore the scope that was current before `span` started, if `span` started one."""
