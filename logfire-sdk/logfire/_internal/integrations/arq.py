from __future__ import annotations

from typing import Any

try:
    from opentelemetry.instrumentation.arq import ArqInstrumentor
except ModuleNotFoundError as exc:
    if exc.name not in {'opentelemetry.instrumentation', 'opentelemetry.instrumentation.arq', 'arq'}:
        raise
    raise RuntimeError(
        '`logfire.instrument_arq()` requires the `arq` and `opentelemetry-instrumentation-arq` packages.\n'
        'You can install these with:\n'
        "    pip install 'logfire[arq]'"
    ) from exc


def instrument_arq(**kwargs: Any) -> None:
    """Instrument ARQ jobs and enqueueing calls.

    See the `Logfire.instrument_arq` method for details.
    """
    return ArqInstrumentor().instrument(**kwargs)
