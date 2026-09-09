"""Logfire having nothing to say, or nothing to say it with: the agent runs exactly as written."""

from __future__ import annotations

import warnings
from typing import Any

import pytest
from agents import Agent, ModelSettings, Runner

from logfire.agent_control.openai_agents import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import FakeModel, FakeProvider, get_weather, publish

pytestmark = pytest.mark.anyio


def controlled(**kwargs: Any) -> tuple[Agent[Any], FakeModel]:
    inner = FakeModel()
    agent = agent_control(
        Agent(
            name='fallback',
            instructions='You are a concise checkout assistant.',
            tools=[get_weather],
            model='m',
            model_settings=ModelSettings(temperature=0.9),
        ),
        provider=FakeProvider({'m': inner}),
        **kwargs,
    )
    return agent, inner


async def test_no_logfire_project_at_all_runs_the_agent_on_its_code() -> None:
    """No `project` fixture: nothing is configured, so there is nothing to resolve and nothing to publish."""
    agent, inner = controlled()
    result = await Runner.run(agent, 'hello')

    assert result.final_output == 'done by fake'
    assert inner.calls[0].system_instructions == 'You are a concise checkout assistant.'
    assert inner.calls[0].tool_names == ['get_weather']
    assert inner.calls[0].model_settings.temperature == 0.9


async def test_an_unreachable_provider_warns_once_and_runs_the_agent_on_its_code(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(project, 'agent__fallback', {'instructions': [{'id': 'agent', 'instructions': 'MANAGED'}]})

    def unreachable(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionError('no route to Logfire')

    monkeypatch.setattr(project, 'get_serialized_value', unreachable)
    agent, inner = controlled(publish_baseline=False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        result = await Runner.run(agent, 'hello')

    assert result.final_output == 'done by fake'
    assert inner.calls[0].system_instructions == 'You are a concise checkout assistant.'
    unreadable = [w for w in caught if 'Failed to read the Logfire managed config' in str(w.message)]
    assert unreadable and 'no route to Logfire' in str(unreadable[0].message)


async def test_a_stored_value_this_release_cannot_parse_costs_only_its_own_piece(
    project: LocalVariableProvider,
) -> None:
    """A bad entry drops itself; everything around it still applies."""
    publish(
        project,
        'agent__fallback',
        {
            'instructions': [{'id': 'agent', 'instructions': ''}, {'instructions': 'ADDED'}],
            'settings': {'temperature': 'warm', 'max_tokens': 42},
        },
    )
    agent, inner = controlled(on_unmatched='ignore')
    with pytest.warns(UserWarning):
        await Runner.run(agent, 'hello')

    assert inner.calls[0].system_instructions == 'You are a concise checkout assistant.\n\nADDED'
    assert inner.calls[0].model_settings.temperature == 0.9
    assert inner.calls[0].model_settings.max_tokens == 42
