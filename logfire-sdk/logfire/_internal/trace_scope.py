"""Context state that lasts for one local trace in this process.

A local root span is the first span that this process starts for a trace: it has no parent, or
its parent came from another process. The span processor sets a fresh `TraceScope` when such a
span starts and restores the previous value when it ends, in the same context. Async tasks and
threads started inside the span share the same `TraceScope` object, so state that one of them
creates is visible to the others. Two requests in different contexts get different scopes, even
if they share a trace ID.
"""

from __future__ import annotations

import threading
from contextvars import ContextVar, Token
from dataclasses import dataclass

from opentelemetry.sdk.trace import ReadableSpan

__all__ = ('TRACE_SCOPE_CONTEXTVAR', 'TraceScope', 'current_trace_scope', 'enter_trace_scope', 'exit_trace_scope')


@dataclass
class TraceScope:
    """Mutable state shared by everything that runs inside one local root span."""

    feature_flag_targeting_key: str | None = None
    """A random targeting key for feature-flag evaluations that do not supply one."""


TRACE_SCOPE_CONTEXTVAR: ContextVar[TraceScope | None] = ContextVar('_TRACE_SCOPE', default=None)
# `on_end` receives a new `ReadableSpan` object, so tokens are keyed by trace and span ID.
_tokens: dict[tuple[int, int] | None, Token[TraceScope | None]] = {}
_tokens_lock = threading.Lock()
# A span that never ends would keep its token forever. Past this many open local root spans, the
# oldest token is dropped, and that span's scope stays set until its context finishes.
_MAX_OPEN_SCOPES = 10_000


def _span_key(span: ReadableSpan) -> tuple[int, int] | None:
    context = span.context
    return None if context is None else (context.trace_id, context.span_id)


def current_trace_scope() -> TraceScope | None:
    """Return the scope of the local trace that the current context belongs to, if any."""
    return TRACE_SCOPE_CONTEXTVAR.get()


def enter_trace_scope(span: ReadableSpan) -> None:
    """Start a new scope in the current context if `span` is a local root span."""
    parent = span.parent
    key = _span_key(span)
    if key is None or (parent is not None and not parent.is_remote):
        return
    token = TRACE_SCOPE_CONTEXTVAR.set(TraceScope())
    with _tokens_lock:
        _tokens[key] = token
        if len(_tokens) > _MAX_OPEN_SCOPES:
            del _tokens[next(iter(_tokens))]


def exit_trace_scope(span: ReadableSpan) -> None:
    """Restore the scope that was current before `span` started, if `span` started one."""
    with _tokens_lock:
        token = _tokens.pop(_span_key(span), None)
    if token is None:
        return
    try:
        TRACE_SCOPE_CONTEXTVAR.reset(token)
    except ValueError:
        # The span ended in a different context from the one that started it. That context
        # never saw the scope, and the starting context discards it when it finishes.
        pass
