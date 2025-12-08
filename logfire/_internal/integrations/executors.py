from __future__ import annotations

from dataclasses import asdict
from functools import partial
from typing import Any, Callable, TypedDict, cast

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


# ---- Minimal typing fix to satisfy pyright ----


class AdvancedConfigDict(TypedDict, total=False):
    exception_callback: Callable[..., Any] | None
    id_generator: Any | None
    ns_timestamp_generator: Any | None
    log_record_processors: Any | None


def serialize_config() -> dict[str, Any]:
    from ..config import GLOBAL_CONFIG

    # note: since `logfire.config._LogfireConfigData` is a dataclass
    # but `LogfireConfig` is not we only get the attributes from `_LogfireConfigData`
    # which is what we want here!
    config_dict = asdict(GLOBAL_CONFIG)

    # Remove non-picklable fields from advanced options
    # exception_callback may be a local function which can't be pickled when using ProcessPoolExecutor
    # See: https://github.com/pydantic/logfire/issues/1556
    if 'advanced' in config_dict and isinstance(config_dict['advanced'], dict):
        config_dict['advanced'] = cast(AdvancedConfigDict, config_dict['advanced']).copy()
        # exception_callback cannot be pickled if it's a local function
        config_dict['advanced'].pop('exception_callback', None)
        # id_generator and ns_timestamp_generator are handled specially during deserialization
        # but they may not be picklable, so we exclude them and use defaults in child processes
        config_dict['advanced'].pop('id_generator', None)
        config_dict['advanced'].pop('ns_timestamp_generator', None)
        # log_record_processors may contain non-picklable objects
        config_dict['advanced'].pop('log_record_processors', None)

    return config_dict


def deserialize_config(config: dict[str, Any]) -> None:
    from ..config import GLOBAL_CONFIG, configure

    if not GLOBAL_CONFIG._initialized:  # type: ignore
        configure(**config)
