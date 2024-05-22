from typing import Any

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor


def instrument_sqlalchemy(**kwargs: Any):
    """Instrument the `sqlalchemy` module so that spans are automatically created for each query.

    See the `Logfire.instrument_sqlalchemy` method for details.
    """
    SQLAlchemyInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
