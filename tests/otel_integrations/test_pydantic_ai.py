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

    # In pydantic-ai >= 1.97, `_get_model` always returns the plain model and
    # instrumentation is resolved separately via `_resolve_instrumentation_settings`
    # and applied later in the run.
    def resolve(a: Agent):
        return a._resolve_instrumentation_settings()  # type: ignore

    # This is the default.
    Agent.instrument_all(False)
    assert resolve(agent1) is None

    # Instrument a single agent.
    logfire_inst.instrument_pydantic_ai(agent1)
    s = resolve(agent1)
    assert isinstance(s, InstrumentationSettings)
    assert s.version == InstrumentationSettings().version
    assert isinstance(s.tracer, _ProxyTracer)
    assert s.tracer.provider is logfire_inst.config.get_tracer_provider()

    # Other agents are unaffected.
    assert resolve(agent2) is None

    # Now instrument all agents. Also specify the current version explicitly.
    logfire_inst.instrument_pydantic_ai(version=5, include_binary_content=False)
    s = resolve(agent1)
    assert isinstance(s, InstrumentationSettings)
    # agent1 still has its own instrumentation settings which override the global ones.
    assert s.version == InstrumentationSettings().version
    assert s.include_binary_content == InstrumentationSettings().include_binary_content
    # agent2 uses the global settings.
    s2 = resolve(agent2)
    assert isinstance(s2, InstrumentationSettings)
    assert s2.version == 5
    assert not s2.include_binary_content

    # Remove the global instrumentation. agent1 remains instrumented.
    Agent.instrument_all(False)
    s = resolve(agent1)
    assert isinstance(s, InstrumentationSettings)
    assert resolve(agent2) is None

    # Test all known parameters
    logfire_inst.instrument_pydantic_ai(
        include_binary_content=False,
        include_content=False,
        version=5,
    )
    s = resolve(agent2)
    assert isinstance(s, InstrumentationSettings)
    assert s.version == 5
    assert not s.include_binary_content
    assert not s.include_content
    Agent.instrument_all(False)


def test_invalid_instrument_pydantic_ai():
    with pytest.raises(TypeError):
        logfire.instrument_pydantic_ai(42)  # type: ignore
