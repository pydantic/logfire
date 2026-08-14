from __future__ import annotations

from opentelemetry.trace import TracerProvider

try:
    from opentelemetry.instrumentation.pymssql import PyMSSQLInstrumentor
except ModuleNotFoundError as error:
    if error.name != 'opentelemetry.instrumentation.pymssql':
        raise
    raise RuntimeError(
        '`logfire.instrument_pymssql()` requires the `opentelemetry-instrumentation-pymssql` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[pymssql]'"
    ) from error


def instrument_pymssql(*, tracer_provider: TracerProvider) -> None:
    """Instrument the `pymssql` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_pymssql` method for details.
    """
    PyMSSQLInstrumentor().instrument(tracer_provider=tracer_provider)
