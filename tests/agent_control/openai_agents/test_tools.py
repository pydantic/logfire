"""Renaming a tool: what the model is offered, what the code runs, and what the history says."""

from __future__ import annotations

from typing import Any

import pytest
from agents import Agent, ModelSettings, Runner, RunResultStreaming, WebSearchTool
from agents.items import ToolCallItem
from agents.stream_events import RawResponsesStreamEvent
from agents.tool import FunctionTool
from inline_snapshot import snapshot
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputItemDoneEvent

from logfire.agent_control.openai_agents import agent_control
from logfire.agent_control.openai_agents._tools import rename_history
from logfire.variables.local import LocalVariableProvider

from .conftest import FakeModel, FakeProvider, get_weather, publish, text_output, tool_call

pytestmark = pytest.mark.anyio

RENAME = {'tool_definitions': [{'name': 'get_weather', 'new_name': 'weather_lookup', 'description': 'Managed.'}]}


def renaming_agent(project: LocalVariableProvider, value: Any = RENAME) -> tuple[Agent[Any], FakeModel]:
    publish(project, 'agent__renamer', value)
    inner = FakeModel(outputs=[[tool_call('weather_lookup')], [text_output('done')]])
    agent = Agent(name='renamer', instructions='Hi.', tools=[get_weather], model='m')
    return agent_control(agent, provider=FakeProvider({'m': inner})), inner


async def test_a_renamed_call_reaches_the_tool_the_code_wrote(project: LocalVariableProvider) -> None:
    agent, inner = renaming_agent(project)
    result = await Runner.run(agent, 'weather?')

    assert inner.calls[0].tool_names == ['weather_lookup']
    assert inner.calls[0].tool('weather_lookup').description == 'Managed.'
    # The runner found the tool, ran it, and recorded the call under the name the code gave it.
    calls = [
        item.raw_item.name
        for item in result.new_items
        if isinstance(item, ToolCallItem) and isinstance(item.raw_item, ResponseFunctionToolCall)
    ]
    assert calls == snapshot(['get_weather'])
    assert result.final_output == 'done'


async def test_the_model_sees_its_own_earlier_call_under_the_managed_name(
    project: LocalVariableProvider,
) -> None:
    agent, inner = renaming_agent(project)
    await Runner.run(agent, 'weather?')

    assert inner.calls[1].history_calls == snapshot(['weather_lookup'])


async def test_a_rename_onto_a_name_in_use_is_refused(project: LocalVariableProvider) -> None:
    """The description still applies; every tool keeps a name the model can call."""

    lookup = FunctionTool(
        name='lookup',
        description='Look something up.',
        params_json_schema={'type': 'object', 'properties': {}},
        on_invoke_tool=get_weather.on_invoke_tool,
    )
    publish(
        project,
        'agent__collide',
        {'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup', 'description': 'Managed.'}]},
    )
    inner = FakeModel()
    agent = agent_control(
        Agent(name='collide', instructions='Hi.', tools=[get_weather, lookup], model='m'),
        provider=FakeProvider({'m': inner}),
    )
    with pytest.warns(UserWarning, match='already advertised by another tool'):
        await Runner.run(agent, 'hello')

    assert inner.calls[0].tool_names == ['get_weather', 'lookup']
    assert inner.calls[0].tool('get_weather').description == 'Managed.'


async def test_an_untouched_tool_is_the_agents_own_object(project: LocalVariableProvider) -> None:
    """No override, no copy: the runner's list reaches the model exactly as assembled."""
    publish(project, 'agent__untouched', {'settings': {'temperature': 0.5}})
    inner = FakeModel()
    agent = agent_control(
        Agent(name='untouched', instructions='Hi.', tools=[get_weather], model='m'),
        provider=FakeProvider({'m': inner}),
    )
    await Runner.run(agent, 'hello')

    assert inner.calls[0].tools[0] is get_weather


async def test_a_renamed_call_is_routed_back_while_streaming(project: LocalVariableProvider) -> None:
    agent, inner = renaming_agent(project)
    streamed: RunResultStreaming = Runner.run_streamed(agent, 'weather?')
    item_names: list[str] = []
    async for event in streamed.stream_events():
        if isinstance(event, RawResponsesStreamEvent) and isinstance(event.data, ResponseOutputItemDoneEvent):
            if isinstance(event.data.item, ResponseFunctionToolCall):
                item_names.append(event.data.item.name)

    assert inner.calls[0].tool_names == ['weather_lookup']
    assert item_names == snapshot(['get_weather'])
    assert inner.calls[1].history_calls == snapshot(['weather_lookup'])
    assert streamed.final_output == 'done'


async def test_streaming_without_a_published_config_is_untouched(project: LocalVariableProvider) -> None:
    inner = FakeModel()
    agent = agent_control(
        Agent(name='streamer', instructions='Hi.', tools=[get_weather], model='m'),
        provider=FakeProvider({'m': inner}),
    )
    streamed = Runner.run_streamed(agent, 'hello')
    async for _ in streamed.stream_events():
        pass

    assert streamed.final_output == 'done by fake'
    assert inner.calls[0].tool_names == ['get_weather']


def test_a_prompt_only_input_has_no_tool_calls_to_rename() -> None:
    """The model interface allows a bare string input, which carries no history at all."""
    assert rename_history('hello', {'get_weather': 'weather_lookup'}) == 'hello'


async def test_a_forced_tool_choice_follows_the_rename(project: LocalVariableProvider) -> None:
    """`tool_choice` names a tool in the same namespace as the tool list, so it is mapped with it."""
    publish(project, 'agent__chooser', RENAME)
    inner = FakeModel()
    agent = agent_control(
        Agent(
            name='chooser',
            instructions='Hi.',
            tools=[get_weather],
            model='m',
            model_settings=ModelSettings(tool_choice='get_weather'),
        ),
        provider=FakeProvider({'m': inner}),
    )
    await Runner.run(agent, 'hello')

    assert inner.calls[0].tool_names == ['weather_lookup']
    assert inner.calls[0].model_settings.tool_choice == 'weather_lookup'


@pytest.mark.parametrize('mode', ['auto', 'required', 'none'])
async def test_a_tool_choice_mode_is_never_read_as_a_name(project: LocalVariableProvider, mode: str) -> None:
    publish(project, f'agent__mode_{mode}', RENAME)
    inner = FakeModel()
    agent = agent_control(
        Agent(
            name=f'mode_{mode}',
            instructions='Hi.',
            tools=[get_weather],
            model='m',
            model_settings=ModelSettings(tool_choice=mode),
        ),
        provider=FakeProvider({'m': inner}),
    )
    await Runner.run(agent, 'hello')

    assert inner.calls[0].model_settings.tool_choice == mode


@pytest.mark.parametrize('mode', ['auto', 'required', 'none'])
async def test_a_rename_onto_a_tool_choice_mode_is_refused(project: LocalVariableProvider, mode: str) -> None:
    """The three names a `tool_choice` is read as a mode under are as reserved as a handoff's.

    Renaming a tool to `auto` would carry a forced `tool_choice` onto it -- and then be read on the
    other side as "let the model choose", turning a code-defined "this call must use this tool" into
    its opposite, with nothing in the published value asking for that.
    """
    publish(
        project,
        f'agent__forced_{mode}',
        {'tool_definitions': [{'name': 'get_weather', 'new_name': mode, 'description': 'Managed.'}]},
    )
    inner = FakeModel()
    agent = agent_control(
        Agent(
            name=f'forced_{mode}',
            instructions='Hi.',
            tools=[get_weather],
            model='m',
            model_settings=ModelSettings(tool_choice='get_weather'),
        ),
        provider=FakeProvider({'m': inner}),
        on_unmatched='ignore',
    )
    await Runner.run(agent, 'hello')

    # The rename is dropped, so the tool keeps its name and the forced choice still forces it.
    assert inner.calls[0].tool_names == ['get_weather']
    assert inner.calls[0].model_settings.tool_choice == 'get_weather'
    # The rest of that override still applies, which is what refusing only the rename means.
    assert inner.calls[0].tool('get_weather').description == 'Managed.'


async def test_a_rename_onto_a_handoff_is_refused(project: LocalVariableProvider) -> None:
    """A handoff is a tool to the model but not one this adapter can rename, so its name is reserved."""
    specialist = Agent(name='specialist', instructions='I specialise.')
    publish(
        project,
        'agent__delegator',
        {'tool_definitions': [{'name': 'get_weather', 'new_name': 'transfer_to_specialist'}]},
    )
    inner = FakeModel()
    agent = agent_control(
        Agent(name='delegator', instructions='Hi.', tools=[get_weather], handoffs=[specialist], model='m'),
        provider=FakeProvider({'m': inner}),
    )
    with pytest.warns(UserWarning, match='already advertised by another tool'):
        await Runner.run(agent, 'hello')

    assert inner.calls[0].tool_names == ['get_weather']


async def test_a_rename_onto_a_hosted_tools_name_is_refused(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__searcher',
        {'tool_definitions': [{'name': 'get_weather', 'new_name': 'web_search'}]},
    )
    inner = FakeModel()
    agent = agent_control(
        Agent(name='searcher', instructions='Hi.', tools=[WebSearchTool(), get_weather], model='m'),
        provider=FakeProvider({'m': inner}),
    )
    with pytest.warns(UserWarning, match='already advertised by another tool'):
        await Runner.run(agent, 'hello')

    assert inner.calls[0].tool_names == snapshot(['web_search', 'get_weather'])
