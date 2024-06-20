from _typeshed import Incomplete
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from logfire.propagate import ContextCarrier as ContextCarrier, attach_context as attach_context, get_context as get_context
from typing import Any, Callable

submit_t_orig: Incomplete
submit_p_orig: Incomplete

def instrument_executors() -> None:
    """Monkey-patch `submit()` methods of `ThreadPoolExecutor` and `ProcessPoolExecutor`
        to carry over OTEL context across threads and processes.
        """
def submit_t(s: ThreadPoolExecutor, fn: Callable[..., Any], /, *args: Any, **kwargs: Any):
    """A wrapper around ThreadPoolExecutor.submit() that carries over OTEL context across threads."""
def submit_p(s: ProcessPoolExecutor, fn: Callable[..., Any], /, *args: Any, **kwargs: Any):
    """A wrapper around ProcessPoolExecutor.submit() that carries over OTEL context across processes."""
def serialize_config() -> dict[str, Any]: ...
def deserialize_config(config: dict[str, Any]) -> None: ...
