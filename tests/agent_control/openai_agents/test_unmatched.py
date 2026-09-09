"""Published values that reach nothing here: warned about, or refused, but never silently dropped."""

from __future__ import annotations

import warnings
from typing import Any

import pytest
from agents import Agent, ModelSettings, Runner
from inline_snapshot import snapshot

from logfire.agent_control import OnUnmatched
from logfire.agent_control.openai_agents import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import FakeModel, FakeProvider, FakeResponsesModel, get_weather, publish

pytestmark = pytest.mark.anyio

UNMATCHED: dict[str, Any] = {
    'instructions': [{'id': 'toolset:legacy_crm', 'instructions': 'Never mind.'}],
    'tool_definitions': [{'name': 'send_email', 'description': 'Managed.'}],
    'settings': {'timeout': 30, 'seed': 7, 'sampling_strategy': 'greedy'},
}


def controlled(project: LocalVariableProvider, on_unmatched: OnUnmatched, value: Any = UNMATCHED) -> Agent[Any]:
    publish(project, 'agent__unmatched', value)
    return agent_control(
        Agent(name='unmatched', instructions='Hi.', tools=[get_weather], model='m'),
        provider=FakeProvider({'m': FakeModel()}),
        on_unmatched=on_unmatched,
    )


async def test_every_kind_of_unmatched_entry_is_named(project: LocalVariableProvider) -> None:
    """One warning each, and each one names what was published and what it did not reach."""
    agent = controlled(project, 'warn')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        await Runner.run(agent, 'hello')

    assert sorted(str(warning.message) for warning in caught) == snapshot(
        [
            "Managed agent config addresses instruction block 'toolset:legacy_crm', which this request does not "
            'assemble; that entry applies to nothing.',
            "Managed agent config patches tool 'send_email', which no toolset advertises for this request; that "
            'override applies to nothing.',
            "Managed agent config sets 'sampling_strategy', which this version of the Agent Control contract has "
            'no model setting for; that key is not applied.',
            "Managed agent config sets 'seed', which this agent framework has no equivalent for; that key is not "
            'applied.',
            "Managed agent config sets 'timeout', which this agent framework has no equivalent for; that key is "
            'not applied.',
        ]
    )


async def test_error_refuses_the_request(project: LocalVariableProvider) -> None:
    agent = controlled(project, 'error')
    with pytest.raises(ValueError, match="instruction block 'toolset:legacy_crm'"):
        await Runner.run(agent, 'hello')


async def test_ignore_says_nothing_and_applies_the_rest(project: LocalVariableProvider) -> None:
    agent = controlled(project, 'ignore', {**UNMATCHED, 'settings': {**UNMATCHED['settings'], 'temperature': 0.4}})
    result = await Runner.run(agent, 'hello')

    assert result.final_output == 'done by fake'


async def test_penalties_are_reported_where_the_responses_api_would_not_send_them(
    project: LocalVariableProvider,
) -> None:
    """`ModelSettings` carries them, the Responses model never sends them, so publishing one is a gap."""
    publish(project, 'agent__responses', {'settings': {'presence_penalty': 0.5, 'temperature': 0.4}})
    responses_model = FakeResponsesModel()
    agent = agent_control(
        Agent(name='responses', instructions='Hi.', model='m', model_settings=ModelSettings()),
        provider=FakeProvider({'m': responses_model}),
    )
    with pytest.warns(UserWarning, match="sets 'presence_penalty', which this agent framework has no equivalent"):
        await Runner.run(agent, 'hello')
    assert responses_model.calls[0].model_settings.presence_penalty is None
    assert responses_model.calls[0].model_settings.temperature == 0.4

    # The same value reaches a model that does send it.
    inner = FakeModel()
    publish(project, 'agent__chatty', {'settings': {'presence_penalty': 0.5}})
    chatty = agent_control(
        Agent(name='chatty', instructions='Hi.', model='m', model_settings=ModelSettings()),
        provider=FakeProvider({'m': inner}),
    )
    await Runner.run(chatty, 'hello')
    assert inner.calls[0].model_settings.presence_penalty == 0.5
