from dataclasses import dataclass
from opentelemetry.sdk.trace import ReadableSpan

__all__ = ['enter_trace_scope', 'exit_trace_scope', 'feature_flag_targeting_key']

@dataclass
class _TraceState:
    open_local_roots: int = ...
    feature_flag_targeting_key: str | None = ...

def enter_trace_scope(span: ReadableSpan) -> None:
    """Count `span` if it is a local root span."""
def exit_trace_scope(span: ReadableSpan) -> None:
    """Discard the trace's state when its last open local root span ends."""
def feature_flag_targeting_key() -> str | None:
    """Return a random targeting key shared by the current trace, or None outside a tracked trace."""
