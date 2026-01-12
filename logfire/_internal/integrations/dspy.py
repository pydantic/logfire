from importlib import import_module, util
from typing import Any

import logfire


def _get_dspy_instrumentor():
    if util.find_spec('openinference.instrumentation.dspy') is None:
        raise RuntimeError(
            'The `logfire.instrument_dspy()` method '
            'requires the `openinference-instrumentation-dspy` package.\n'
            'You can install this with:\n'
            "    pip install 'logfire[dspy]'"
        )
    module = import_module('openinference.instrumentation.dspy')
    return module.DSPyInstrumentor


def instrument_dspy(logfire_instance: logfire.Logfire, **kwargs: Any):
    dspy_instrumentor = _get_dspy_instrumentor()
    dspy_instrumentor().instrument(
        tracer_provider=logfire_instance.config.get_tracer_provider(),
        **kwargs,
    )
