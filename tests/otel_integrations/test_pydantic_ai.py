import sys
from typing import TYPE_CHECKING

import pydantic
import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.exporters.test import TestExporter
from logfire._internal.tracer import _ProxyTracer  # type: ignore
from logfire._internal.utils import get_version

try:
    from pydantic_ai import Agent
    from pydantic_ai.exceptions import ApprovalRequired, CallDeferred
    from pydantic_ai.models.instrumented import InstrumentationSettings, InstrumentedModel
    from pydantic_ai.models.test import TestModel

except Exception:
    assert not TYPE_CHECKING
    # Provide fallback values so @pytest.mark.parametrize can resolve at module level;
    # tests using these will be skipped by pytestmark on unsupported Python/Pydantic versions.
    CallDeferred = type('CallDeferred', (Exception,), {})  # type: ignore
    ApprovalRequired = type('ApprovalRequired', (Exception,), {})  # type: ignore

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

    # Test all known parameters
    logfire_inst.instrument_pydantic_ai(
        include_binary_content=False,
        include_content=False,
        version=1,
        event_mode='logs',
    )
    m = get_model(agent2)
    assert isinstance(m, InstrumentedModel)
    assert m.instrumentation_settings.version == 1
    assert not m.instrumentation_settings.include_binary_content
    assert not m.instrumentation_settings.include_content
    assert m.instrumentation_settings.event_mode == 'logs'
    Agent.instrument_all(False)


def test_invalid_instrument_pydantic_ai():
    with pytest.raises(TypeError):
        logfire.instrument_pydantic_ai(42)  # type: ignore


@pytest.mark.parametrize('exc_class', [CallDeferred, ApprovalRequired])
def test_call_deferred_not_recorded_as_error(exporter: TestExporter, exc_class: type[Exception]):
    """CallDeferred and ApprovalRequired are control flow exceptions in pydantic-ai.

    They should not be recorded as errors or set the span level to error.
    """
    with pytest.raises(exc_class):
        with logfire.span('tool call'):
            raise exc_class()

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'tool call',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_pydantic_ai.py',
                    'code.function': 'test_call_deferred_not_recorded_as_error',
                    'code.lineno': 123,
                    'logfire.msg_template': 'tool call',
                    'logfire.msg': 'tool call',
                    'logfire.span_type': 'span',
                },
            }
        ]
    )
