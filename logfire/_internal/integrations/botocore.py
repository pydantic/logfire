from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias

from opentelemetry._logs import LoggerProvider
from opentelemetry.metrics import MeterProvider
from opentelemetry.propagators.textmap import TextMapPropagator
from opentelemetry.trace import Span, TracerProvider

RequestHook: TypeAlias = Callable[[Span, str, str, dict[str, Any]], None]
ResponseHook: TypeAlias = Callable[[Span, str, str, Any], None]

try:
    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
except ModuleNotFoundError as error:
    if error.name != 'opentelemetry.instrumentation.botocore':
        raise
    raise RuntimeError(
        '`logfire.instrument_botocore()` requires the `opentelemetry-instrumentation-botocore` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[botocore]'"
    ) from error


def instrument_botocore(
    *,
    request_hook: RequestHook | None,
    response_hook: ResponseHook | None,
    propagator: TextMapPropagator | None,
    tracer_provider: TracerProvider,
    meter_provider: MeterProvider,
    logger_provider: LoggerProvider,
) -> None:
    """Instrument botocore clients so that spans are automatically created for AWS API calls.

    See the `Logfire.instrument_botocore` method for details.
    """
    BotocoreInstrumentor().instrument(
        request_hook=request_hook,
        response_hook=response_hook,
        propagator=propagator,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
    )
