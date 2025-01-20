from __future__ import annotations

from dataclasses import asdict
from functools import partial
from typing import Any, Callable

from logfire.propagate import ContextCarrier, attach_context, get_context

try:
    # concurrent.futures does not work in pyodide

    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

    submit_t_orig = ThreadPoolExecutor.submit
    submit_p_orig = ProcessPoolExecutor.submit

    def instrument_executors() -> None:
        """Monkey-patch `submit()` methods of `ThreadPoolExecutor` and `ProcessPoolExecutor`
        to carry over OTEL context across threads and processes.
        """  # noqa: D205
        global submit_t_orig, submit_p_orig
        if ThreadPoolExecutor.submit is submit_t_orig:
            ThreadPoolExecutor.submit = submit_t
        if ProcessPoolExecutor.submit is submit_p_orig:
            ProcessPoolExecutor.submit = submit_p

    def submit_t(s: ThreadPoolExecutor, fn: Callable[..., Any], /, *args: Any, **kwargs: Any):
        """A wrapper around ThreadPoolExecutor.submit() that carries over OTEL context across threads."""
        fn = partial(fn, *args, **kwargs)
        carrier = get_context()
        return submit_t_orig(s, _run_with_context, carrier=carrier, func=fn, parent_config=None)

    def submit_p(s: ProcessPoolExecutor, fn: Callable[..., Any], /, *args: Any, **kwargs: Any):
        """A wrapper around ProcessPoolExecutor.submit() that carries over OTEL context across processes."""
        fn = partial(fn, *args, **kwargs)
        carrier = get_context()
        return submit_p_orig(s, _run_with_context, carrier=carrier, func=fn, parent_config=serialize_config())

    def _run_with_context(
        carrier: ContextCarrier, func: Callable[[], Any], parent_config: dict[str, Any] | None
    ) -> Any:
        """A wrapper around a function that restores OTEL context from a carrier and then calls the function.

        This gets run from within a process / thread.
        """
        if parent_config is not None:
            deserialize_config(parent_config)  # pragma: no cover

        with attach_context(carrier):
            return func()

except ImportError:  # pragma: no cover

    def instrument_executors() -> None:
        pass


def serialize_config() -> dict[str, Any]:
    from ..config import GLOBAL_CONFIG

    # note: since `logfire.config._LogfireConfigData` is a dataclass
    # but `LogfireConfig` is not we only get the attributes from `_LogfireConfigData`
    # which is what we want here!
    return asdict(GLOBAL_CONFIG)


def deserialize_config(config: dict[str, Any]) -> None:
    from ..config import GLOBAL_CONFIG, configure

    if not GLOBAL_CONFIG._initialized:  # type: ignore
        configure(**config)
