from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict
from functools import partial
from typing import Any, Callable

from opentelemetry import context, propagate

submit_t_orig = ThreadPoolExecutor.submit
submit_p_orig = ProcessPoolExecutor.submit


def instrument_executors() -> None:
    """
    Monkey-patch submit() methods of ThreadPoolExecutor and ProcessPoolExecutor to carry over OTEL context
    across threads and processes.
    """
    global submit_t_orig, submit_p_orig
    if ThreadPoolExecutor.submit is submit_t_orig:
        ThreadPoolExecutor.submit = submit_t
    if ProcessPoolExecutor.submit is submit_p_orig:
        ProcessPoolExecutor.submit = submit_p


def submit_t(s: ThreadPoolExecutor, fn: Callable[..., Any], /, *args: Any, **kwargs: Any):
    """A wrapper around ThreadPoolExecutor.submit() that carries over OTEL context across threads."""
    fn = partial(fn, *args, **kwargs)
    carrier: dict[str, Any] = {}
    propagate.inject(carrier)
    return submit_t_orig(s, _run_with_context, carrier=carrier, fn=fn, parent_config=None)


def submit_p(s: ProcessPoolExecutor, fn: Callable[..., Any], /, *args: Any, **kwargs: Any):
    """A wrapper around ProcessPoolExecutor.submit() that carries over OTEL context across processes."""
    from logfire import _config  # type: ignore

    # note: since `logfire.config._LogfireConfigData` is a dataclass
    # but `LogfireConfig` is not we only get the attributes from `_LogfireConfigData`
    # which is what we want here!
    new_config = asdict(_config.GLOBAL_CONFIG)

    fn = partial(fn, *args, **kwargs)
    carrier: dict[str, Any] = {}
    propagate.inject(carrier)
    return submit_p_orig(s, _run_with_context, carrier=carrier, fn=fn, parent_config=new_config)


def _run_with_context(carrier: dict[str, Any], fn: Callable[[], Any], parent_config: dict[str, Any] | None) -> Any:
    """A wrapper around a function that restores OTEL context from a carrier and then calls the function.

    This gets run from within a process / thread.
    """
    if parent_config is not None:
        from logfire import _config  # type: ignore

        _config.configure(**parent_config)

    # capture the current context to restore it later
    old_context = context.get_current()
    new_context = propagate.extract(carrier=carrier)
    try:
        context.attach(new_context)
        return fn()
    finally:
        context.attach(old_context)
