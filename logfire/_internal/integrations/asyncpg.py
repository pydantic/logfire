from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor


def instrument_asyncpg():
    """Instrument the `asyncpg` module so that spans are automatically created for each query.

    See the `Logfire.instrument_asyncpg` method for details.
    """
    AsyncPGInstrumentor().instrument()  # type: ignore[reportUnknownMemberType]
