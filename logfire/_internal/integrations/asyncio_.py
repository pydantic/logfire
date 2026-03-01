from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..main import Logfire

try:
    from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_asyncio()` requires the `opentelemetry-instrumentation-asyncio` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[asyncio]'"
    )


def instrument_asyncio(
    logfire_instance: Logfire,
    slow_duration: float = 0.1,
    **kwargs: Any,
) -> AbstractContextManager[None]:
    """Instrument asyncio to trace coroutines, futures, and detect slow callbacks.

    See the `Logfire.instrument_asyncio` method for details.
    """
    from ..async_ import log_slow_callbacks

    AsyncioInstrumentor().instrument(**kwargs)
    return log_slow_callbacks(logfire_instance, slow_duration)
