"""State that lasts while a trace has open local root spans in this process.

A local root span is the first span that this process starts for a trace: it has no parent, or its
parent came from another process. The span processor records the open local root spans of each trace
and discards the trace's state when the last one ends. The tracer records local root spans that a
sampler dropped, because processors never see them. Work in any thread or task that belongs to the
trace shares the state. A later request that reuses the trace ID after it ended gets new state.
"""

from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass, field

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import get_current_span

__all__ = (
    'enter_local_root',
    'enter_trace_scope',
    'exit_local_root',
    'exit_trace_scope',
    'feature_flag_targeting_key',
)


@dataclass
class _TraceState:
    # Span IDs, not a count: a root whose state was evicted must not end a later state for the
    # same trace ID.
    open_local_roots: set[int] = field(default_factory=set[int])
    feature_flag_targeting_key: str | None = None


_states: dict[int, _TraceState] = {}
_lock = threading.Lock()
# A span that never ends would keep its trace's state forever. Past this many traces with open
# local root spans, the oldest state is discarded.
_MAX_OPEN_TRACES = 10_000
# Many requests can reuse one remote trace ID. Past this many open local root spans in one trace, a
# new root span is not recorded. Its end then has no effect, so it cannot discard state that other
# root spans still use. Work in an unrecorded root span can get a different fallback key.
_MAX_OPEN_ROOTS_PER_TRACE = 1_000


def _local_root_ids(span: ReadableSpan) -> tuple[int, int] | None:
    parent = span.parent
    context = span.context
    if context is None or (parent is not None and not parent.is_remote):
        return None
    return context.trace_id, context.span_id


def _reset_lock_after_fork() -> None:  # pragma: no cover
    # Every local root span takes this lock. If another thread held it when the process forked,
    # the child would wait for it forever. The child keeps the states, because work in the child
    # can continue a trace that was open in the parent.
    global _lock
    _lock = threading.Lock()


if hasattr(os, 'register_at_fork'):  # pragma: no branch
    os.register_at_fork(after_in_child=_reset_lock_after_fork)


def enter_trace_scope(span: ReadableSpan) -> None:
    """Record `span` if it is a local root span."""
    ids = _local_root_ids(span)
    if ids is not None:
        enter_local_root(*ids)


def enter_local_root(trace_id: int, span_id: int) -> None:
    """Record an open local root span by its IDs."""
    with _lock:
        state = _states.setdefault(trace_id, _TraceState())
        if len(state.open_local_roots) >= _MAX_OPEN_ROOTS_PER_TRACE:
            return
        state.open_local_roots.add(span_id)
        if len(_states) > _MAX_OPEN_TRACES:
            del _states[next(iter(_states))]


def exit_trace_scope(span: ReadableSpan) -> None:
    """Discard the trace's state when its last open local root span ends."""
    ids = _local_root_ids(span)
    if ids is not None:
        exit_local_root(*ids)


def exit_local_root(trace_id: int, span_id: int) -> None:
    """Forget an open local root span, and discard its trace's state if it was the last one."""
    with _lock:
        state = _states.get(trace_id)
        if state is None or span_id not in state.open_local_roots:
            return
        state.open_local_roots.discard(span_id)
        if not state.open_local_roots:
            del _states[trace_id]


def feature_flag_targeting_key() -> str | None:
    """Return a random targeting key shared by the current trace, or None outside a tracked trace."""
    trace_id = get_current_span().get_span_context().trace_id
    if not trace_id:
        return None
    with _lock:
        state = _states.get(trace_id)
        if state is None:
            return None
        if state.feature_flag_targeting_key is None:
            state.feature_flag_targeting_key = f'trace:{secrets.token_hex(16)}'
        return state.feature_flag_targeting_key
