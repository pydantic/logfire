import sys
from typing import TYPE_CHECKING

import pydantic
import pytest

import logfire
from logfire._internal.tracer import _ProxyTracer  # type: ignore
from logfire._internal.utils import get_version

try:
    from pydantic_ai import Agent
    from pydantic_ai.models.instrumented import InstrumentationSettings, InstrumentedModel
    from pydantic_ai.models.test import TestModel

except Exception:
    assert not TYPE_CHECKING

pytestmark = [
    pytest.mark.skipif(sys.version_info < (3, 10), reason='Pydantic AI requires Python 3.10 or higher'),
    pytest.mark.skipif(
        get_version(pydantic.__version__) < get_version('2.10'), reason='Pydantic AI requires Pydantic 2.10 or higher'
    ),
]


@pytest.mark.anyio
async def test_instrument_pydantic_ai():
    logfire_inst = logfire.configure(local=True)

    model = TestModel()

    # Instrumenting a model returns a new model and leaves the original as is.
    instrumented = logfire_inst.instrument_pydantic_ai(model)
    assert isinstance(instrumented, InstrumentedModel)
    assert isinstance(model, TestModel)

    agent1 = Agent()
    agent2 = Agent()

    def get_model(a: Agent):
        return a._get_model(model)  # type: ignore

    # This is the default.
    Agent.instrument_all(False)
    assert get_model(agent1) is model

    # Instrument a single agent.
    logfire_inst.instrument_pydantic_ai(agent1)
    m = get_model(agent1)
    assert isinstance(m, InstrumentedModel)
    assert m.wrapped is model
    assert m.instrumentation_settings.version == InstrumentationSettings().version
    assert isinstance(m.instrumentation_settings.tracer, _ProxyTracer)
    assert m.instrumentation_settings.tracer.provider is logfire_inst.config.get_tracer_provider()

    # Other agents are unaffected.
    m2 = get_model(agent2)
    assert m2 is model

    # Now instrument all agents. Also use the (currently not default) version
    logfire_inst.instrument_pydantic_ai(version=1, include_binary_content=False)
    m = get_model(agent1)
    assert isinstance(m, InstrumentedModel)
    # agent1 still has its own instrumentation settings which override the global ones.
    assert m.instrumentation_settings.version == InstrumentationSettings().version
    assert m.instrumentation_settings.include_binary_content == InstrumentationSettings().include_binary_content
    # agent2 uses the global settings.
    m2 = get_model(agent2)
    assert isinstance(m2, InstrumentedModel)
    assert m2.instrumentation_settings.version == 1
    assert not m2.instrumentation_settings.include_binary_content

    # Remove the global instrumentation. agent1 remains instrumented.
    Agent.instrument_all(False)
    m = get_model(agent1)
    assert isinstance(m, InstrumentedModel)
    m2 = get_model(agent2)
    assert m2 is model


def test_invalid_instrument_pydantic_ai():
    with pytest.raises(TypeError):
        logfire.instrument_pydantic_ai(42)  # type: ignore
