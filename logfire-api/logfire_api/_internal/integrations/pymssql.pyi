from opentelemetry.trace import TracerProvider

def instrument_pymssql(*, tracer_provider: TracerProvider) -> None:
    """Instrument the `pymssql` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_pymssql` method for details.
    """
