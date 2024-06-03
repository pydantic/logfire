from typing import Any

from opentelemetry.instrumentation.redis import RedisInstrumentor


def instrument_redis(**kwargs: Any):
    """Instrument the `redis` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_redis` method for details.
    """
    RedisInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
