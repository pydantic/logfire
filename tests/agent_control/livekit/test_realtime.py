"""A realtime model never reaches `llm_node`: what can be told to the session, and what cannot."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from livekit.agents import Agent, AgentSession, RunContext, llm

from logfire.variables.local import LocalVariableProvider

from ..conftest import publish
from .agents import CONTEXTS, convert_currency, convert_currency_sync, get_weather, lookup_order, managed, names, run
from .conftest import clear
from .stubs import StubLLM, StubRealtimeModel

pytestmark = pytest.mark.anyio


def doorbell(**options: Any) -> Callable[[], Agent]:
    return managed('doorbell', instructions='Answer the door.', **options)


async def enter(agent: Agent, model: StubRealtimeModel) -> None:
    session = AgentSession(llm=model)
    await session.start(agent)
    await session.aclose()


async def a_run_context() -> RunContext[Any]:
    """A real `RunContext`, taken from a tool call in a real turn of a stateless agent."""
    await run(managed('capture', tools=[get_weather])(), StubLLM(tool_call='get_weather'))
    return CONTEXTS[-1]


async def test_instructions_and_tools_are_sent_to_the_session(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__doorbell',
        {
            'instructions': [{'id': 'agent', 'instructions': 'PUBLISHED'}],
            'tool_definitions': [{'name': 'get_weather', 'new_name': 'fetch_weather', 'description': 'Fetch it.'}],
        },
    )
    model = StubRealtimeModel()
    agent = doorbell(tools=[get_weather, llm.Toolset(id='orders', tools=[lookup_order])])()
    with pytest.warns(UserWarning, match="renames tool 'get_weather' to 'fetch_weather'"):
        await enter(agent, model)

    assert model.updates.instructions[-1] == 'PUBLISHED'
    # The clone a realtime session gets is real: dispatch is the same name lookup, so the code sees
    # the new name too, which is why the rename is reported.
    assert sorted(names(model.updates.tools[-1])) == ['fetch_weather', 'lookup_order']
    assert names(agent.tools) == ['fetch_weather']


async def test_a_patched_parameter_is_still_executable(project: LocalVariableProvider) -> None:
    """The realtime tool list *is* the dispatcher, so a raw clone has to run the tool it cloned."""
    publish(
        project,
        'agent__doorbell',
        {'tool_definitions': [{'name': 'convert_currency', 'parameters': {'to': {'description': 'ISO code.'}}}]},
    )
    model = StubRealtimeModel()
    await enter(doorbell(tools=[convert_currency])(), model)

    installed = model.updates.tools[-1]
    assert isinstance(installed[0], llm.RawFunctionTool)
    assert installed[0].info.raw_schema['parameters']['properties']['to']['description'] == 'ISO code.'
    result = await llm.utils.execute_function_call(
        llm.FunctionToolCall(name='convert_currency', arguments='{"amount": 12, "to": "EUR"}', call_id='call-1'),
        llm.ToolContext(installed),
    )
    assert result.fnc_call_out is not None and result.fnc_call_out.output == '12.0 EUR'


async def test_a_patched_parameter_on_a_sync_tool_is_still_executable(project: LocalVariableProvider) -> None:
    """`@function_tool` takes a sync function too, and the bridge has to run one without awaiting it."""
    publish(
        project,
        'agent__doorbell',
        {'tool_definitions': [{'name': 'convert_currency_sync', 'parameters': {'to': {'description': 'ISO code.'}}}]},
    )
    model = StubRealtimeModel()
    await enter(doorbell(tools=[convert_currency_sync])(), model)

    installed = model.updates.tools[-1]
    assert isinstance(installed[0], llm.RawFunctionTool)
    result = await llm.utils.execute_function_call(
        llm.FunctionToolCall(name='convert_currency_sync', arguments='{"amount": 12, "to": "EUR"}', call_id='call-1'),
        llm.ToolContext(installed),
    )
    assert result.fnc_call_out is not None and result.fnc_call_out.output == 'sync 12.0 EUR'


async def test_a_patched_parameter_still_validates_and_injects_the_context(
    project: LocalVariableProvider,
) -> None:
    """The bridge asks LiveKit for the original tool's own argument handling, not a raw passthrough."""
    publish(
        project,
        'agent__doorbell',
        {'tool_definitions': [{'name': 'get_weather', 'parameters': {'city': {'description': 'A city.'}}}]},
    )
    model = StubRealtimeModel()
    await enter(doorbell(tools=[get_weather])(), model)
    installed = llm.ToolContext(model.updates.tools[-1])
    ctx = await a_run_context()

    called = await llm.utils.execute_function_call(
        llm.FunctionToolCall(name='get_weather', arguments='{"city": "Paris"}', call_id='call-1'),
        installed,
        call_ctx=ctx,
    )
    assert called.fnc_call_out is not None and called.fnc_call_out.output == 'weather(get_weather, Paris)'

    missing = await llm.utils.execute_function_call(
        llm.FunctionToolCall(name='get_weather', arguments='{}', call_id='call-2'),
        installed,
        call_ctx=ctx,
    )
    assert missing.fnc_call_out is not None and missing.fnc_call_out.is_error


async def test_a_model_and_settings_are_reported_as_unapplied(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__doorbell',
        {'model': 'openai:gpt-realtime', 'settings': {'temperature': 0.4}},
    )
    with pytest.warns(UserWarning) as caught:
        await enter(doorbell()(), StubRealtimeModel())
    messages = {str(warning.message) for warning in caught}
    assert any('cannot be moved to another model' in message for message in messages)
    assert any(
        "sets 'temperature', which this agent framework has no equivalent for" in message for message in messages
    )


async def test_a_session_that_cannot_be_updated_is_reported(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__doorbell',
        {
            'instructions': [{'id': 'agent', 'instructions': 'PUBLISHED'}],
            'tool_definitions': [{'name': 'get_weather', 'description': 'Fetch it.'}],
        },
    )
    model = StubRealtimeModel(mutable_instructions=False, mutable_tools=False)
    with pytest.warns(UserWarning) as caught:
        await enter(doorbell(tools=[get_weather])(), model)
    messages = {str(warning.message) for warning in caught}
    assert any('sets instructions, which this realtime model cannot be told mid-session' in m for m in messages)
    assert any('patches tool definitions, which this realtime model cannot be told' in m for m in messages)
    assert model.updates.instructions == ['Answer the door.']


async def test_nothing_published_leaves_the_session_alone(project: LocalVariableProvider) -> None:
    model = StubRealtimeModel()
    await enter(doorbell(tools=[get_weather])(), model)
    assert model.updates.instructions == ['Answer the door.']
    assert names(model.updates.tools[-1]) == ['get_weather']


async def test_an_override_for_a_toolset_tool_reaches_nothing(project: LocalVariableProvider) -> None:
    """Realtime tools are replaced in place, and a toolset is not this package's to rebuild."""
    publish(project, 'agent__doorbell', {'tool_definitions': [{'name': 'lookup_order', 'description': 'X'}]})
    agent = doorbell(tools=[llm.Toolset(id='orders', tools=[lookup_order])])()
    with pytest.warns(UserWarning, match="patches tool 'lookup_order', which no toolset advertises"):
        await enter(agent, StubRealtimeModel())


async def test_a_rename_onto_a_toolset_tool_is_refused(project: LocalVariableProvider) -> None:
    """A realtime `Toolset` is carried across untouched, so its names are not a rename's to take.

    `update_tools` keeps one of two tools sharing a name, silently, which would leave the session
    with a tool it can no longer call.
    """
    publish(
        project,
        'agent__doorbell',
        {'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup_order', 'description': 'Reworded.'}]},
    )
    model = StubRealtimeModel()
    agent = doorbell(tools=[get_weather, llm.Toolset(id='orders', tools=[lookup_order])])()
    with pytest.warns(UserWarning, match="renames 'get_weather' to 'lookup_order', which is already advertised"):
        await enter(agent, model)

    # The rename is dropped and the rest of the override still applies, so both tools survive.
    assert names(model.updates.tools[-1]) == ['get_weather', 'lookup_order']


async def test_re_entry_after_a_withdrawal_puts_the_code_side_back(project: LocalVariableProvider) -> None:
    """Publish, re-enter, withdraw, re-enter: the agent has to end up exactly where it started."""
    publish(
        project,
        'agent__doorbell',
        {
            'instructions': [{'id': 'agent', 'instructions': 'PUBLISHED'}, 'AND MORE'],
            'tool_definitions': [{'name': 'get_weather', 'new_name': 'fetch_weather'}],
        },
    )
    model = StubRealtimeModel()
    agent = doorbell(tools=[get_weather])()
    with pytest.warns(UserWarning, match="renames tool 'get_weather' to 'fetch_weather'"):
        await enter(agent, model)
        # Re-entering with the same value applies the same thing rather than layering another copy.
        await enter(agent, model)
    assert model.updates.instructions[-1] == 'PUBLISHED\n\nAND MORE'
    assert names(agent.tools) == ['fetch_weather']

    clear(project, 'agent__doorbell')
    await enter(agent, model)
    assert model.updates.instructions[-1] == 'Answer the door.'
    assert agent.tools == [get_weather]
    assert agent.instructions == 'Answer the door.'


async def test_a_prompt_the_user_replaced_becomes_the_code_side(project: LocalVariableProvider) -> None:
    """An `update_instructions()` of the user's own is theirs, and survives a withdrawal."""
    publish(project, 'agent__doorbell', {'instructions': [{'id': 'agent', 'instructions': 'PUBLISHED'}]})
    model = StubRealtimeModel()
    agent = doorbell(tools=[get_weather])()
    session = AgentSession(llm=model)
    await session.start(agent)
    try:
        await agent.update_instructions('THEIRS')
        await agent.update_tools([get_weather, lookup_order])
    finally:
        await session.aclose()
    clear(project, 'agent__doorbell')
    await enter(agent, model)
    assert agent.instructions == 'THEIRS'
    assert names(agent.tools) == ['get_weather', 'lookup_order']
