from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from opentelemetry.context import Context
    from opentelemetry.instrumentation.aws_lambda import AwsLambdaInstrumentor
    from opentelemetry.metrics import MeterProvider
    from opentelemetry.trace import TracerProvider
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_aws_lambda()` requires the `opentelemetry-instrumentation-aws-lambda` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[aws-lambda]'"
    )

if TYPE_CHECKING:
    from typing import Any, Callable, TypedDict, Unpack

    LambdaEvent = Any

    class AwsLambdaInstrumentKwargs(TypedDict, total=False):
        skip_dep_check: bool
        event_context_extractor: Callable[[LambdaEvent], Context]


def instrument_aws_lambda(
    lambda_function: Any,
    *,
    tracer_provider: TracerProvider,
    meter_provider: MeterProvider,
    **kwargs: Unpack[AwsLambdaInstrumentKwargs],
) -> None:
    """Instrument the AWS Lambda runtime so that spans are automatically created for each invocation.

    See the `Logfire.instrument_aws_lambda` method for details.
    """
    return AwsLambdaInstrumentor().instrument(  # type: ignore[no-any-return]
        tracer_provider=tracer_provider, meter_provider=meter_provider, **kwargs
    )
