import sys
from typing import TYPE_CHECKING

import pydantic
import pytest

import logfire
from logfire._internal.tracer import _ProxyTracer  # type: ignore

try:
    from pydantic_ai import Agent
    from pydantic_ai.models.instrumented import InstrumentationSettings, InstrumentedModel
    from pydantic_ai.models.test import TestModel

except (ImportError, AttributeError):
    pytestmark = pytest.mark.skipif(
        sys.version_info < (3, 9) or pydantic.__version__.startswith('2.4'),
        reason='Requires Python 3.9 or higher and Pydantic 2.5 or higher',
    )
    if TYPE_CHECKING:
        assert False


def test_instrument_pydantic_ai():
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
    assert m.settings.event_mode == InstrumentationSettings().event_mode == 'attributes'
    assert isinstance(m.settings.tracer, _ProxyTracer)
    assert m.settings.tracer.provider is logfire_inst.config.get_tracer_provider()

    # Other agents are unaffected.
    m2 = get_model(agent2)
    assert m2 is model

    # Now instrument all agents. Also use the (currently not default) event mode.
    logfire_inst.instrument_pydantic_ai(event_mode='logs', include_binary_content=False)
    m = get_model(agent1)
    assert isinstance(m, InstrumentedModel)
    # agent1 still has its own instrumentation settings which override the global ones.
    assert m.settings.event_mode == InstrumentationSettings().event_mode == 'attributes'
    assert m.settings.include_binary_content == InstrumentationSettings().include_binary_content
    # agent2 uses the global settings.
    m2 = get_model(agent2)
    assert isinstance(m2, InstrumentedModel)
    assert m2.settings.event_mode == 'logs'
    assert not m2.settings.include_binary_content

    # Remove the global instrumentation. agent1 remains instrumented.
    Agent.instrument_all(False)
    m = get_model(agent1)
    assert isinstance(m, InstrumentedModel)
    m2 = get_model(agent2)
    assert m2 is model


def test_invalid_instrument_pydantic_ai():
    with pytest.raises(TypeError):
        logfire.instrument_pydantic_ai(42)  # type: ignore
