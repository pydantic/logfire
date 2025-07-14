from typing import Any

from openinference.instrumentation.litellm import LiteLLMInstrumentor

import logfire


def instrument_litellm(logfire_instance: logfire.Logfire, **kwargs: Any):
    LiteLLMInstrumentor().instrument(
        tracer_provider=logfire_instance.config.get_tracer_provider(),
        **kwargs,
    )
