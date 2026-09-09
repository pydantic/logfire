"""The baseline the adapter publishes: the agent as written, as the Logfire editor opens on it."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from agents import Agent, ModelSettings, RunContextWrapper, Runner, WebSearchTool
from agents.tool import FunctionTool, ToolOrigin, ToolOriginType
from inline_snapshot import snapshot
from openai.types.shared.reasoning import Reasoning

from logfire.agent_control.openai_agents import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import (
    FakeModel,
    FakeProvider,
    FakeResponsesModel,
    controlled,
    get_weather,
    published_example,
    wait_for_baseline,
)

pytestmark = pytest.mark.anyio


async def run_once(agent: Agent[Any], **kwargs: Any) -> None:
    """Run one turn, which is when the adapter can first describe the whole agent, and publish."""
    await Runner.run(agent, 'hello', **kwargs)
    wait_for_baseline(agent)


async def test_publishes_the_agent_as_written(project: LocalVariableProvider) -> None:
    agent = agent_control(
        Agent(
            name='checkout_assistant',
            instructions='You are a concise checkout assistant.',
            tools=[get_weather],
            model='litellm/anthropic/claude-fable-5-1',
            model_settings=ModelSettings(temperature=0.1, reasoning=Reasoning(effort='high')),
        ),
        provider=FakeProvider(),
    )
    await run_once(agent)

    assert published_example(project, 'agent__checkout_assistant') == snapshot(
        {
            'instructions': [
                {'id': 'agent', 'instructions': 'You are a concise checkout assistant.', 'dynamic': False}
            ],
            'model': 'anthropic:claude-fable-5-1',
            'settings': {'temperature': 0.1, 'thinking': 'high'},
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'description': 'Get the current weather for a city.',
                    'parameters': {'city': {'description': 'City to look up.'}},
                    'toolset': '<agent>',
                }
            ],
        }
    )


async def test_a_computed_prompt_is_published_as_a_seam_without_its_text(project: LocalVariableProvider) -> None:
    def instructions(context: RunContextWrapper[Any], agent: Agent[Any]) -> str:
        return f'You serve {context.context}.'

    agent = agent_control(Agent(name='tenant_assistant', instructions=instructions), provider=FakeProvider())
    await run_once(agent, context='acme')

    assert published_example(project, 'agent__tenant_assistant') == snapshot(
        {
            'instructions': [{'id': 'agent', 'dynamic': True}],
            'model': 'openai:gpt-5.6-luna',
            'settings': {'thinking': False},
        }
    )


async def test_declared_blocks_are_published_one_by_one(project: LocalVariableProvider) -> None:
    agent = agent_control(
        Agent(name='blocked_assistant', model='gpt-5.6-luna', model_settings=ModelSettings()),
        instructions={
            'today': lambda context, agent: f'Today is {date(2026, 9, 9)}.',
            'agent': 'You are a concise checkout assistant.',
            'refunds': 'Always confirm the order total.',
        },
        provider=FakeProvider(),
    )
    await run_once(agent)

    assert published_example(project, 'agent__blocked_assistant') == snapshot(
        {
            'instructions': [
                {'id': 'agent', 'instructions': 'You are a concise checkout assistant.', 'dynamic': False},
                {'id': 'refunds', 'instructions': 'Always confirm the order total.', 'dynamic': False},
                {'id': 'today', 'dynamic': True},
            ],
            'model': 'openai:gpt-5.6-luna',
        }
    )


async def test_tools_are_grouped_by_where_they_came_from(project: LocalVariableProvider) -> None:
    """A tool an MCP server contributed, and an agent exposed as a tool, name their own group."""
    mcp_tool = FunctionTool(
        name='search',
        description='Search the CRM.',
        params_json_schema={'type': 'object', 'properties': {}},
        on_invoke_tool=get_weather.on_invoke_tool,
        _tool_origin=ToolOrigin(type=ToolOriginType.MCP, mcp_server_name='crm'),
    )
    delegated = FunctionTool(
        name='ask_specialist',
        description='Ask the specialist.',
        params_json_schema={'type': 'object', 'properties': {}},
        on_invoke_tool=get_weather.on_invoke_tool,
        _tool_origin=ToolOrigin(type=ToolOriginType.AGENT_AS_TOOL, agent_name='specialist'),
    )
    agent = agent_control(
        Agent(name='grouped', tools=[mcp_tool, delegated, get_weather], model='gpt-5.6-luna'),
        provider=FakeProvider(),
    )
    await run_once(agent)

    example = published_example(project, 'agent__grouped')
    assert [(entry['name'], entry['toolset']) for entry in example['tool_definitions']] == snapshot(
        [('search', 'mcp:crm'), ('ask_specialist', 'agent:specialist'), ('get_weather', '<agent>')]
    )


async def test_hosted_tools_and_unmappable_settings_are_left_out(project: LocalVariableProvider) -> None:
    """A hosted tool shows the model no description of its own, and a provider-specific setting is not one.

    An effort the contract has no word for is left out too, and said out loud rather than published as
    its nearest neighbour: `'max'` is not `'xhigh'`, and a baseline is read as what the code does.
    """
    agent = agent_control(
        Agent(
            name='hosted',
            instructions='Search the web.',
            tools=[WebSearchTool()],
            model='gpt-5.6-luna',
            model_settings=ModelSettings(reasoning=Reasoning(effort='max'), extra_headers={'x': 'y'}),
        ),
        provider=FakeProvider(),
    )
    with pytest.warns(UserWarning, match="runs with thinking='max', which the Agent Control contract cannot"):
        await run_once(agent)

    assert published_example(project, 'agent__hosted') == snapshot(
        {
            'instructions': [{'id': 'agent', 'instructions': 'Search the web.', 'dynamic': False}],
            'model': 'openai:gpt-5.6-luna',
        }
    )


@pytest.mark.parametrize('model', [FakeModel('code'), FakeResponsesModel('unnamed')])
async def test_a_model_object_with_no_name_publishes_no_model(project: LocalVariableProvider, model: FakeModel) -> None:
    """A `Model` the SDK cannot read a name off has no model *name* to publish, and still runs."""
    agent = agent_control(Agent(name='object_model', instructions='Hi.', model=model))
    await run_once(agent)

    assert published_example(project, 'agent__object_model') == snapshot(
        {'instructions': [{'id': 'agent', 'instructions': 'Hi.', 'dynamic': False}]}
    )
    assert len(model.calls) == 1


async def test_the_baseline_is_built_once_per_wrapper(project: LocalVariableProvider) -> None:
    agent = agent_control(Agent(name='once', instructions='Hi.', model='gpt-5.6-luna'), provider=FakeProvider())
    await run_once(agent)
    assert controlled(agent)._published is True  # pyright: ignore[reportPrivateUsage]

    await Runner.run(agent, 'again')
    assert published_example(project, 'agent__once')['instructions'][0]['instructions'] == 'Hi.'


@pytest.mark.parametrize('enabled', [False, True])
async def test_publishing_can_be_turned_off(project: LocalVariableProvider, enabled: bool) -> None:
    agent = agent_control(
        Agent(name='quiet', instructions='Hi.', model='gpt-5.6-luna'),
        provider=FakeProvider(),
        publish_baseline=enabled,
    )
    await run_once(agent)
    assert (project.get_variable_config('agent__quiet') is not None) is enabled


async def test_the_baseline_describes_only_the_settings_the_code_model_would_send(
    project: LocalVariableProvider,
) -> None:
    """The Responses API has no request field for either penalty, so neither is a knob to offer."""
    responses_model = FakeResponsesModel()
    agent = agent_control(
        Agent(
            name='penalised',
            instructions='Hi.',
            model='m',
            model_settings=ModelSettings(temperature=0.3, presence_penalty=0.5, frequency_penalty=0.5),
        ),
        provider=FakeProvider({'m': responses_model}),
    )
    await run_once(agent)

    assert published_example(project, 'agent__penalised')['settings'] == snapshot({'temperature': 0.3})


async def test_a_baseline_names_the_model_an_sdk_model_object_was_built_with(
    project: LocalVariableProvider,
) -> None:
    """One of the SDK's own OpenAI models carries its name, so the baseline can say what the code runs."""
    responses_model = FakeResponsesModel()
    responses_model.model = 'gpt-5.6-luna'
    agent = agent_control(Agent(name='named_object', instructions='Hi.', model=responses_model))
    await run_once(agent)

    assert published_example(project, 'agent__named_object')['model'] == 'openai:gpt-5.6-luna'
