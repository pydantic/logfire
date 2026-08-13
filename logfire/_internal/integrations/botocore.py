from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias

from opentelemetry.trace import Span

RequestHook: TypeAlias = Callable[[Span, str, str, dict[str, Any]], None]
ResponseHook: TypeAlias = Callable[[Span, str, str, Any], None]

try:
    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_botocore()` requires the `opentelemetry-instrumentation-botocore` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[botocore]'"
    )


def instrument_botocore(**kwargs: Any) -> None:
    """Instrument botocore clients so that spans are automatically created for AWS API calls.

    See the `Logfire.instrument_botocore` method for details.
    """
    BotocoreInstrumentor().instrument(**kwargs)
