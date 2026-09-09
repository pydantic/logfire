"""Each managed section, applied to a real run against a fake model."""

from __future__ import annotations

from typing import Any

import pytest
from agents import Agent, ModelSettings, RunConfig, RunContextWrapper, RunHooks, Runner, WebSearchTool
from agents.run_config import CallModelData, ModelInputData
from inline_snapshot import snapshot
from openai.types.shared.reasoning import Reasoning

from logfire.agent_control.openai_agents import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import FakeModel, FakeProvider, get_weather, publish, wait_for_baseline

pytestmark = pytest.mark.anyio


def controlled_agent(**kwargs: Any) -> tuple[Agent[Any], FakeModel]:
    """An agent whose model is a fake one, wrapped for Agent Control."""
    inner = FakeModel()
    provider = FakeProvider({'gpt-5.6-luna': inner})
    fields: dict[str, Any] = {
        'name': 'checkout_assistant',
        'instructions': 'You are a concise checkout assistant.',
        'tools': [get_weather],
        'model': 'gpt-5.6-luna',
        'model_settings': ModelSettings(temperature=0.9, top_p=0.5),
        **kwargs,
    }
    return agent_control(Agent(**fields), provider=provider), inner


async def test_nothing_published_runs_the_agent_as_written(project: LocalVariableProvider) -> None:
    agent, inner = controlled_agent()
    result = await Runner.run(agent, 'hello')

    assert result.final_output == 'done by fake'
    assert inner.calls[0].system_instructions == 'You are a concise checkout assistant.'
    assert inner.calls[0].tool_names == ['get_weather']
    assert (inner.calls[0].model_settings.temperature, inner.calls[0].model_settings.top_p) == (0.9, 0.5)


async def test_published_instructions_replace_and_add_blocks(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__checkout_assistant',
        {
            'instructions': [
                {'id': 'agent', 'instructions': 'MANAGED PROMPT'},
                {'instructions': 'ADDED BLOCK'},
            ]
        },
    )
    agent, inner = controlled_agent()
    await Runner.run(agent, 'hello')

    assert inner.calls[0].system_instructions == snapshot("""\
MANAGED PROMPT

ADDED BLOCK\
""")


async def test_a_published_block_can_be_dropped(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout_assistant', {'instructions': [{'id': 'agent'}]})
    agent, inner = controlled_agent()
    await Runner.run(agent, 'hello')

    # Nothing is left to send, which is the SDK's own way of saying an agent has no prompt.
    assert inner.calls[0].system_instructions is None


async def test_declared_blocks_are_addressed_one_at_a_time(project: LocalVariableProvider) -> None:
    publish(project, 'agent__blocked', {'instructions': [{'id': 'refunds', 'instructions': 'No refunds.'}]})
    inner = FakeModel()
    agent = agent_control(
        Agent(name='blocked', model='m'),
        instructions={
            'agent': 'You are a concise checkout assistant.',
            'refunds': 'Always confirm the order total.',
            'today': lambda context, agent: f'You serve {context.context}.',
        },
        provider=FakeProvider({'m': inner}),
    )
    await Runner.run(agent, 'hello', context='acme')

    assert inner.calls[0].system_instructions == snapshot(
        """\
You are a concise checkout assistant.

No refunds.

You serve acme.\
"""
    )


async def test_a_computed_block_is_never_replaced(project: LocalVariableProvider) -> None:
    """Replacing a per-request block would pin one rendering of it, so it is refused and reported."""
    publish(project, 'agent__blocked', {'instructions': [{'id': 'today', 'instructions': 'Today is never.'}]})
    inner = FakeModel()
    agent = agent_control(
        Agent(name='blocked', model='m'),
        instructions={'today': lambda context, agent: f'You serve {context.context}.'},
        provider=FakeProvider({'m': inner}),
        on_unmatched='ignore',
    )
    await Runner.run(agent, 'hello', context='acme')

    assert inner.calls[0].system_instructions == 'You serve acme.'


async def test_an_added_block_lands_inside_the_cacheable_prefix(project: LocalVariableProvider) -> None:
    publish(project, 'agent__blocked', {'instructions': 'ADDED'})
    inner = FakeModel()
    agent = agent_control(
        Agent(name='blocked', model='m'),
        instructions={
            'today': lambda context, agent: 'Today is Tuesday.',
            'agent': 'You are a concise checkout assistant.',
        },
        provider=FakeProvider({'m': inner}),
    )
    await Runner.run(agent, 'hello')

    assert inner.calls[0].system_instructions == snapshot(
        """\
You are a concise checkout assistant.

ADDED

Today is Tuesday.\
"""
    )


async def test_an_agent_with_no_prompt_can_still_be_given_one(project: LocalVariableProvider) -> None:
    publish(project, 'agent__silent', {'instructions': 'ADDED'})
    inner = FakeModel()
    agent = agent_control(Agent(name='silent', model='m'), provider=FakeProvider({'m': inner}))
    await Runner.run(agent, 'hello')

    assert inner.calls[0].system_instructions == 'ADDED'


async def test_published_settings_are_lowered_onto_the_request(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__checkout_assistant',
        {'settings': {'temperature': 0.1, 'max_tokens': 50, 'thinking': 'high', 'parallel_tool_calls': True}},
    )
    agent, inner = controlled_agent(model_settings=ModelSettings(temperature=0.9, reasoning=Reasoning(summary='auto')))
    await Runner.run(agent, 'hello')

    settings = inner.calls[0].model_settings
    assert (settings.temperature, settings.max_tokens, settings.parallel_tool_calls) == (0.1, 50, True)
    # The effort is overlaid onto the agent's own `Reasoning`, so what nobody published survives.
    assert settings.reasoning == snapshot(Reasoning(effort='high', summary='auto'))


async def test_thinking_as_a_flag_is_lowered_to_an_effort(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout_assistant', {'settings': {'thinking': True}})
    agent, inner = controlled_agent()
    await Runner.run(agent, 'hello')
    assert inner.calls[0].model_settings.reasoning == snapshot(Reasoning(effort='medium'))

    publish(project, 'agent__off', {'settings': {'thinking': False}})
    off = FakeModel()
    agent = agent_control(Agent(name='off', instructions='Hi.', model='m'), provider=FakeProvider({'m': off}))
    await Runner.run(agent, 'hello')
    assert off.calls[0].model_settings.reasoning == snapshot(Reasoning(effort='none'))


async def test_a_published_model_replaces_the_one_in_code(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout_assistant', {'model': 'anthropic:claude-fable-5-1'})
    code = FakeModel('code')
    managed = FakeModel('managed')
    provider = FakeProvider({'gpt-5.6-luna': code, 'litellm/anthropic/claude-fable-5-1': managed})
    agent = agent_control(Agent(name='checkout_assistant', instructions='Hi.', model='gpt-5.6-luna'), provider=provider)
    result = await Runner.run(agent, 'hello')

    assert result.final_output == 'done by managed'
    assert code.calls == []
    # The code model is resolved too, once: describing the agent as written in the baseline includes
    # which of its settings that model would actually send.
    assert provider.requested == snapshot(['gpt-5.6-luna', 'litellm/anthropic/claude-fable-5-1'])


async def test_a_published_model_the_contract_cannot_classify_is_passed_through(
    project: LocalVariableProvider,
) -> None:
    publish(project, 'agent__checkout_assistant', {'model': 'my-gateway/some-model'})
    provider = FakeProvider()
    agent = agent_control(Agent(name='checkout_assistant', instructions='Hi.', model='gpt-5.6-luna'), provider=provider)
    await Runner.run(agent, 'hello')

    assert provider.requested == snapshot(['gpt-5.6-luna', 'my-gateway/some-model'])


async def test_published_tool_definitions_reach_the_model(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__checkout_assistant',
        {
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'description': 'Managed description.',
                    'parameters': {'city': {'description': 'Managed parameter description.'}},
                }
            ]
        },
    )
    agent, inner = controlled_agent()
    await Runner.run(agent, 'hello')

    advertised = inner.calls[0].tool('get_weather')
    assert advertised.description == 'Managed description.'
    assert advertised.params_json_schema['properties']['city']['description'] == 'Managed parameter description.'
    # The agent's own tool is untouched, so another agent sharing it is unaffected.
    assert get_weather.description == 'Get the current weather for a city.'


async def test_the_code_agent_is_not_modified(project: LocalVariableProvider) -> None:
    code_agent = Agent(name='checkout_assistant', instructions='Hi.', model='gpt-5.6-luna')
    managed = agent_control(code_agent, provider=FakeProvider())

    assert code_agent.instructions == 'Hi.'
    assert code_agent.model == 'gpt-5.6-luna'
    assert managed is not code_agent


async def test_hooks_and_input_filters_see_the_managed_prompt(project: LocalVariableProvider) -> None:
    """Instructions are applied where they are assembled, so a filter still has the last word."""
    publish(project, 'agent__checkout_assistant', {'instructions': [{'id': 'agent', 'instructions': 'MANAGED'}]})
    seen: list[str | None] = []

    class Hooks(RunHooks[Any]):
        async def on_llm_start(
            self,
            context: RunContextWrapper[Any],
            agent: Agent[Any],
            system_prompt: str | None,
            input_items: Any,
        ) -> None:
            seen.append(system_prompt)

    def filter_input(data: CallModelData[Any]) -> ModelInputData:
        return ModelInputData(input=data.model_data.input, instructions=f'{data.model_data.instructions} + FILTERED')

    agent, inner = controlled_agent()
    await Runner.run(agent, 'hello', hooks=Hooks(), run_config=RunConfig(call_model_input_filter=filter_input))

    # The hook runs after the filter, so both see the managed text and the filter's rewrite reaches
    # the model: applying instructions where they are assembled leaves the SDK's own order intact.
    assert seen == ['MANAGED + FILTERED']
    assert inner.calls[0].system_instructions == 'MANAGED + FILTERED'


async def test_the_baseline_publishes_alongside_an_applied_config(project: LocalVariableProvider) -> None:
    """Publishing a value does not stop the baseline being published for the editor to diff against."""
    publish(project, 'agent__checkout_assistant', {'model': 'openai:gpt-5.6-luna'})
    agent, _ = controlled_agent()
    await Runner.run(agent, 'hello')
    wait_for_baseline(agent)

    config = project.get_variable_config('agent__checkout_assistant')
    assert config is not None and config.example is not None


async def test_a_block_written_as_a_coroutine_is_awaited(project: LocalVariableProvider) -> None:
    publish(project, 'agent__async_blocks', {'instructions': [{'id': 'agent', 'instructions': 'MANAGED'}]})

    async def tenant(context: RunContextWrapper[Any], agent: Agent[Any]) -> str:
        return f'You serve {context.context}.'

    inner = FakeModel()
    agent = agent_control(
        Agent(name='async_blocks', model='m'),
        instructions={'agent': 'Hi.', 'tenant': tenant},
        provider=FakeProvider({'m': inner}),
    )
    await Runner.run(agent, 'hello', context='acme')

    assert inner.calls[0].system_instructions == snapshot("""\
MANAGED

You serve acme.\
""")


async def test_a_hosted_tool_passes_through_a_managed_tool_list(project: LocalVariableProvider) -> None:
    """Hosted tools have nothing to patch, and keep the place the runner gave them."""
    publish(
        project,
        'agent__hosted',
        {'tool_definitions': [{'name': 'get_weather', 'new_name': 'weather_lookup'}]},
    )
    inner = FakeModel()
    agent = agent_control(
        Agent(name='hosted', instructions='Hi.', tools=[WebSearchTool(), get_weather], model='m'),
        provider=FakeProvider({'m': inner}),
    )
    await Runner.run(agent, 'hello')

    assert inner.calls[0].tool_names == snapshot(['web_search', 'weather_lookup'])
    assert inner.calls[0].tools[0] is agent.tools[0]
