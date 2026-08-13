from __future__ import annotations

from typing import Any

from opentelemetry.trace import TracerProvider

try:
    from opentelemetry.instrumentation.pymssql import PyMSSQLInstrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_pymssql()` requires the `opentelemetry-instrumentation-pymssql` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[pymssql]'"
    )


def instrument_pymssql(*, tracer_provider: TracerProvider, **kwargs: Any) -> None:
    """Instrument the `pymssql` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_pymssql` method for details.
    """
    PyMSSQLInstrumentor().instrument(tracer_provider=tracer_provider, **kwargs)
