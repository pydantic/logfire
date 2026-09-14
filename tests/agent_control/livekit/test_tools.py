"""Tool definitions: what the model is shown, and how a call under a new name gets home."""

from __future__ import annotations

import pytest
from livekit.agents import AgentSession, llm

from logfire.variables.local import LocalVariableProvider

from ..conftest import publish
from .agents import ProviderSearch, get_weather, lookup_order, managed, names, outputs, ping, run
from .stubs import StubLLM

pytestmark = pytest.mark.anyio

RENAME = {
    'name': 'get_weather',
    'new_name': 'fetch_weather',
    'description': 'Fetch the weather for a city.',
    'parameters': {'city': {'description': 'City name, e.g. London.'}},
}


async def test_a_renamed_tool_is_advertised_and_routed_back(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'tool_definitions': [RENAME]})
    stub = StubLLM(tool_call='fetch_weather')
    result = await run(managed(tools=[get_weather])(), stub)

    first = stub.requests[0]
    assert first.tool_names == ['fetch_weather']
    assert first.schema('fetch_weather') == {
        'name': 'fetch_weather',
        'description': 'Fetch the weather for a city.',
        'parameters': {
            'properties': {'city': {'description': 'City name, e.g. London.', 'title': 'City', 'type': 'string'}},
            'required': ['city'],
            'title': 'GetWeatherArgs',
            'type': 'object',
        },
    }
    # The implementation runs under its own name, with the arguments the model sent.
    assert outputs(result) == [('get_weather', 'weather(get_weather, Paris)')]
    # And the next request shows the model the history under the name it was given.
    assert stub.requests[1].call_names == ['fetch_weather', 'fetch_weather']


async def test_the_code_tool_is_left_alone(project: LocalVariableProvider) -> None:
    """The clone is advertised; the tool the agent holds keeps its own name and schema."""
    publish(project, 'agent__checkout', {'tool_definitions': [RENAME]})
    agent = managed(tools=[get_weather])()
    await run(agent, StubLLM(tool_call='fetch_weather'))
    assert names(agent.tools) == ['get_weather']
    assert get_weather.info.description == 'Get the current weather for a city.\n'


async def test_a_description_only_change_keeps_the_derived_schema(project: LocalVariableProvider) -> None:
    """No parameter is patched, so the tool stays a `@function_tool` and its schema stays LiveKit's."""
    publish(
        project,
        'agent__checkout',
        {'tool_definitions': [{'name': 'get_weather', 'description': 'Reworded.'}]},
    )
    stub = StubLLM()
    await run(managed(tools=[get_weather])(), stub)
    assert isinstance(stub.requests[0].tools[0], llm.FunctionTool)
    assert stub.requests[0].schema('get_weather')['description'] == 'Reworded.'


async def test_a_raw_schema_tool_is_patched_in_place(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__checkout',
        {
            'tool_definitions': [
                {
                    'name': 'lookup_order',
                    'new_name': 'find_order',
                    'parameters': {'order_id': {'description': 'The order number.'}},
                }
            ]
        },
    )
    stub = StubLLM(tool_call='find_order')
    result = await run(managed(tools=[lookup_order])(), stub)
    assert stub.requests[0].schema('find_order') == {
        'name': 'find_order',
        'description': 'Look up an order.',
        'parameters': {
            'type': 'object',
            'properties': {'order_id': {'type': 'string', 'description': 'The order number.'}},
        },
    }
    assert outputs(result) == [('lookup_order', 'shipped')]


async def test_an_override_can_be_narrowed_to_one_toolset(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__checkout',
        {'tool_definitions': [{'name': 'lookup_order', 'toolset': 'orders', 'description': 'The orders one.'}]},
    )
    stub = StubLLM()
    tools = [get_weather, llm.Toolset(id='orders', tools=[lookup_order])]
    await run(managed(tools=tools)(), stub)
    assert stub.requests[0].schema('lookup_order')['description'] == 'The orders one.'


async def test_a_provider_tool_is_passed_through(project: LocalVariableProvider) -> None:
    """A tool the provider runs has no definition of ours, so it is advertised exactly as given."""
    publish(project, 'agent__checkout', {'tool_definitions': [RENAME]})
    search = ProviderSearch()
    stub = StubLLM()
    await run(managed(tools=[get_weather, search])(), stub)
    assert stub.requests[0].tools[1] is search


async def test_a_rename_onto_a_provider_tool_is_refused(project: LocalVariableProvider) -> None:
    """A provider tool is advertised under its own id, so that id is not a rename's to take."""
    publish(
        project,
        'agent__checkout',
        {'tool_definitions': [{'name': 'get_weather', 'new_name': 'provider_search', 'description': 'Reworded.'}]},
    )
    stub = StubLLM()
    with pytest.warns(UserWarning, match="renames 'get_weather' to 'provider_search', which is already advertised"):
        await run(managed(tools=[get_weather, ProviderSearch()])(), stub)
    # The rename is dropped and the rest of the override still applies.
    assert stub.requests[0].tool_names == ['get_weather']
    assert stub.requests[0].schema('get_weather')['description'] == 'Reworded.'


async def test_a_forced_tool_choice_follows_the_rename(project: LocalVariableProvider) -> None:
    """The code forced one tool; a rename must not quietly unforce it by renaming past the choice."""
    publish(project, 'agent__checkout', {'tool_definitions': [RENAME]})
    stub = StubLLM(tool_call='fetch_weather')
    session = AgentSession(llm=stub)
    await session.start(managed(tools=[get_weather])())
    try:
        await session.generate_reply(
            user_input='hi', tool_choice={'type': 'function', 'function': {'name': 'get_weather'}}
        )
    finally:
        await session.aclose()
    assert stub.requests[0].tool_choice == {'type': 'function', 'function': {'name': 'fetch_weather'}}


async def test_a_tool_choice_that_names_no_tool_is_left_alone(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'tool_definitions': [RENAME]})
    stub = StubLLM()
    session = AgentSession(llm=stub)
    await session.start(managed(tools=[get_weather])())
    try:
        await session.generate_reply(user_input='hi', tool_choice='required')
    finally:
        await session.aclose()
    assert stub.requests[0].tool_choice == 'required'


async def test_a_tool_choice_for_a_tool_nothing_renamed_is_left_alone(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'tool_definitions': [RENAME]})
    stub = StubLLM()
    session = AgentSession(llm=stub)
    await session.start(managed(tools=[get_weather, ping])())
    try:
        await session.generate_reply(user_input='hi', tool_choice={'type': 'function', 'function': {'name': 'ping'}})
    finally:
        await session.aclose()
    assert stub.requests[0].tool_choice == {'type': 'function', 'function': {'name': 'ping'}}


async def test_an_override_no_tool_matches_is_reported(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'tool_definitions': [{'name': 'nonsense', 'description': 'X'}]})
    with pytest.warns(UserWarning, match="patches tool 'nonsense', which no toolset advertises"):
        await run(managed(tools=[get_weather])(), StubLLM())


async def test_an_override_no_tool_matches_can_fail_the_request(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'tool_definitions': [{'name': 'nonsense', 'description': 'X'}]})
    with pytest.raises(ValueError, match="patches tool 'nonsense'"):
        await run(managed(tools=[get_weather], on_unmatched='error')(), StubLLM())


async def test_session_tools_are_managed_too(project: LocalVariableProvider) -> None:
    """A tool the session supplies reaches the same hook, and is grouped by the same toolsets."""
    publish(
        project,
        'agent__checkout',
        {'tool_definitions': [{'name': 'lookup_order', 'toolset': 'orders', 'new_name': 'find_order'}]},
    )
    stub = StubLLM()
    session = AgentSession(llm=stub, tools=[llm.Toolset(id='orders', tools=[lookup_order])])
    await session.start(managed(tools=[get_weather])())
    try:
        await session.run(user_input='hi')
    finally:
        await session.aclose()
    assert sorted(stub.requests[0].tool_names) == ['find_order', 'get_weather']


async def test_a_tool_with_no_description_keeps_having_none(project: LocalVariableProvider) -> None:
    """A rename patches the name and nothing else, so an absent description stays absent."""
    publish(project, 'agent__checkout', {'tool_definitions': [{'name': 'ping', 'new_name': 'health'}]})
    stub = StubLLM(tool_call='health')
    result = await run(managed(tools=[ping])(), stub)
    assert stub.requests[0].schema('health') == {'name': 'health', 'parameters': {'type': 'object', 'properties': {}}}
    assert outputs(result) == [('ping', 'pong')]
