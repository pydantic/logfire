from __future__ import annotations

from typing import Any

try:
    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_botocore()` requires the `opentelemetry-instrumentation-botocore` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[botocore]'"
    )


def instrument_botocore(**kwargs: Any) -> None:
    """Instrument boto3 and botocore clients so that AWS API calls create spans.

    See the `Logfire.instrument_botocore` method for details.
    """
    return BotocoreInstrumentor().instrument(**kwargs)
