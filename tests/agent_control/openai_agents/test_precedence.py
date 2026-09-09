"""Per-run beats published beats code, and what the SDK does not let this adapter reach."""

from __future__ import annotations

import dataclasses

import pytest
from agents import Agent, ModelSettings, RunConfig, Runner
from inline_snapshot import snapshot
from openai.types.shared.reasoning import Reasoning

from logfire.agent_control.openai_agents import agent_control
from logfire.agent_control.openai_agents._adapter import _explicit_fields  # pyright: ignore[reportPrivateUsage]
from logfire.variables.local import LocalVariableProvider

from .conftest import FakeModel, FakeProvider, publish

pytestmark = pytest.mark.anyio

PUBLISHED = {'settings': {'temperature': 0.2, 'max_tokens': 100, 'thinking': 'low'}}


def controlled(project: LocalVariableProvider, **kwargs: object) -> tuple[Agent[object], FakeModel]:
    publish(project, 'agent__precedence', PUBLISHED)
    inner = FakeModel()
    agent = agent_control(
        Agent(name='precedence', instructions='Hi.', model='m', **kwargs),  # type: ignore[arg-type]
        provider=FakeProvider({'m': inner}),
    )
    return agent, inner


async def test_published_settings_beat_the_agents_own(project: LocalVariableProvider) -> None:
    agent, inner = controlled(project, model_settings=ModelSettings(temperature=0.9, top_p=0.5))
    await Runner.run(agent, 'hello')

    settings = inner.calls[0].model_settings
    assert (settings.temperature, settings.max_tokens, settings.top_p) == (0.2, 100, 0.5)


async def test_a_per_run_setting_beats_the_published_one(project: LocalVariableProvider) -> None:
    """The runner merges the two before a model sees either, so the diff against code recovers it."""
    agent, inner = controlled(project, model_settings=ModelSettings(temperature=0.9, top_p=0.5))
    await Runner.run(agent, 'hello', run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, max_tokens=5)))

    settings = inner.calls[0].model_settings
    assert (settings.temperature, settings.max_tokens) == (0.7, 5)
    # Nothing the run did not set is disturbed: `thinking` is still the published one.
    assert settings.reasoning == snapshot(Reasoning(effort='low'))


async def test_a_per_run_reasoning_effort_beats_the_published_one(project: LocalVariableProvider) -> None:
    agent, inner = controlled(project, model_settings=ModelSettings(reasoning=Reasoning(effort='high')))
    await Runner.run(
        agent, 'hello', run_config=RunConfig(model_settings=ModelSettings(reasoning=Reasoning(effort='xhigh')))
    )

    assert inner.calls[0].model_settings.reasoning == snapshot(Reasoning(effort='xhigh'))


async def test_a_per_run_model_bypasses_agent_control(project: LocalVariableProvider) -> None:
    """The runner prefers `RunConfig.model` over the agent's, and the agent's is this adapter."""
    publish(project, 'agent__bypassed', {'settings': {'temperature': 0.2}})
    per_run = FakeModel('per-run')
    agent = agent_control(
        Agent(name='bypassed', instructions='Hi.', model='m', model_settings=ModelSettings(temperature=0.9)),
        provider=FakeProvider(),
    )
    await Runner.run(agent, 'hello', run_config=RunConfig(model=per_run, model_provider=FakeProvider({'m': per_run})))

    assert len(per_run.calls) == 1
    assert per_run.calls[0].model_settings.temperature == 0.9
    # The prompt is still managed: instructions are applied where the agent assembles them.
    assert per_run.calls[0].system_instructions == 'Hi.'


async def test_wrapping_keeps_the_model_defaults_the_sdk_would_have_applied(
    project: LocalVariableProvider,
) -> None:
    """An agent that never touched `model_settings` keeps the reasoning effort its model name implies."""
    code_agent = Agent(name='defaults', instructions='Hi.', model='gpt-5.6-luna')
    inner = FakeModel()
    agent = agent_control(code_agent, provider=FakeProvider({'gpt-5.6-luna': inner}))
    await Runner.run(agent, 'hello')

    assert dataclasses.astuple(agent.model_settings) == dataclasses.astuple(code_agent.model_settings)
    assert inner.calls[0].model_settings.reasoning == snapshot(Reasoning(effort='none'))
    assert inner.calls[0].model_settings.verbosity == 'low'


async def test_a_per_run_value_that_repeats_the_code_value_still_beats_the_published_one(
    project: LocalVariableProvider,
) -> None:
    """The case a diff against the code cannot see, and the reason the run's keys are captured instead.

    Code `0.9`, published `0.2`, and a run that asks for `0.9`: the merged object a model is handed
    looks exactly like a run that asked for nothing, so only the keys the override actually named --
    recorded where the SDK merged them in -- can tell the two apart.
    """
    agent, inner = controlled(project, model_settings=ModelSettings(temperature=0.9))
    await Runner.run(agent, 'hello', run_config=RunConfig(model_settings=ModelSettings(temperature=0.9)))

    assert inner.calls[0].model_settings.temperature == 0.9
    # Everything the run did not name is still the published value.
    assert inner.calls[0].model_settings.max_tokens == 100


async def test_per_run_settings_given_as_a_mapping_are_read_the_same_way(
    project: LocalVariableProvider,
) -> None:
    """`RunConfig(model_settings={...})` is the SDK's other spelling of the same per-run override."""
    agent, inner = controlled(project, model_settings=ModelSettings(temperature=0.9))
    await Runner.run(agent, 'hello', run_config=RunConfig(model_settings={'temperature': 0.9}))

    assert inner.calls[0].model_settings.temperature == 0.9


def test_a_mapping_override_names_the_keys_it_gives_a_value_to() -> None:
    """`ModelSettings.resolve` takes a mapping as well, and reads it the same way the SDK does."""
    assert _explicit_fields({'temperature': 0.9, 'top_p': None, 'truncation': 'auto'}) == {'temperature'}
    assert _explicit_fields(ModelSettings(max_tokens=5)) == {'max_tokens'}
    assert _explicit_fields(None) == frozenset()


async def test_a_run_that_sets_nothing_leaves_the_published_settings_in_place(
    project: LocalVariableProvider,
) -> None:
    agent, inner = controlled(project, model_settings=ModelSettings(temperature=0.9))
    await Runner.run(agent, 'hello', run_config=RunConfig(model_settings=ModelSettings(top_p=0.3)))

    settings = inner.calls[0].model_settings
    assert (settings.temperature, settings.top_p, settings.max_tokens) == (0.2, 0.3, 100)
