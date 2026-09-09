"""What a published `tool_definitions` section does to the tools the model is shown, and to a call."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from inline_snapshot import snapshot
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from logfire.agent_control.langchain import agent_control
from logfire.agent_control.langchain._tools import rename_tool_calls, rename_tool_choice
from logfire.variables.local import LocalVariableProvider

from .conftest import TOOLS, RecordingModel, bound_tools, build_agent, publish, republish, run, weather_call

RENAME: dict[str, Any] = {'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup_weather'}]}


def messages(result: dict[str, Any]) -> list[tuple[str, str, Any]]:
    return [(message.type, message.text, getattr(message, 'name', None)) for message in result['messages']]


def tool_call_names(messages: Sequence[BaseMessage]) -> list[str]:
    """Every tool a conversation calls, by the name the calls give it."""
    return [call['name'] for message in messages if isinstance(message, AIMessage) for call in message.tool_calls]


class ForceTool(AgentMiddleware[Any, Any, Any]):
    """A middleware of the user's own, making the model call one of the code's tools."""

    def __init__(self, name: str) -> None:
        self.tools = []
        self._name = name

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResponse[Any]:
        return handler(request.override(tool_choice={'type': 'function', 'function': {'name': self._name}}))


class WatchToolCalls(AgentMiddleware[Any, Any, Any]):
    """A middleware of the user's own, keyed on the names its code gave its tools."""

    def __init__(self) -> None:
        self.tools = []
        self.seen: list[str] = []

    def wrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]]
    ) -> ToolMessage | Command[Any]:
        self.seen.append(request.tool_call['name'])
        return handler(request)


def test_a_renamed_tool_is_advertised_renamed_and_still_runs_the_code_tool(project: LocalVariableProvider) -> None:
    publish(
        project,
        {
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'new_name': 'lookup_weather',
                    'description': 'Look the weather up.',
                    'parameters': {'city': {'description': "City name, e.g. 'Paris'"}},
                }
            ]
        },
    )
    model = RecordingModel(replies=[weather_call('lookup_weather'), AIMessage('done')])
    result = run(build_agent(model, agent_control(label='production')))

    assert bound_tools(model)[0] == snapshot(
        {
            'name': 'lookup_weather',
            'description': 'Look the weather up.',
            'parameters': {
                'properties': {'city': {'description': "City name, e.g. 'Paris'", 'type': 'string'}},
                'required': ['city'],
                'type': 'object',
            },
        }
    )
    # The implementation ran, under its own name: only what the model is told about a tool is managed.
    assert messages(result) == snapshot(
        [
            ('human', 'weather in Paris?', None),
            ('ai', '', 'checkout'),
            ('tool', 'sunny in Paris', 'get_weather'),
            ('ai', 'done', 'checkout'),
        ]
    )
    # Including the call itself, which is what the graph dispatches, stores and checkpoints.
    assert tool_call_names(result['messages']) == ['get_weather']


def test_the_history_the_model_is_replayed_says_the_names_it_was_shown(project: LocalVariableProvider) -> None:
    publish(project, RENAME)
    model = RecordingModel(replies=[weather_call('lookup_weather'), AIMessage('done')])
    run(build_agent(model, agent_control(label='production')))

    # The second request replays the first turn: the model sees the tool it called, under the name
    # it was shown, even though nothing on this side of the boundary ever held that name.
    assert tool_call_names(model.requests[1]['messages']) == ['lookup_weather']


def test_an_earlier_middlewares_tool_hook_sees_the_code_name(project: LocalVariableProvider) -> None:
    publish(project, RENAME)
    watcher = WatchToolCalls()
    model = RecordingModel(replies=[weather_call('lookup_weather'), AIMessage('done')])
    run(build_agent(model, agent_control(label='production'), before=[watcher]))

    # A middleware installed before this one wraps the tool call from further out, and a rename is
    # not something it should have to know about.
    assert watcher.seen == ['get_weather']


def test_a_rename_that_changes_and_is_withdrawn_keeps_a_resumed_thread_consistent(
    project: LocalVariableProvider,
) -> None:
    publish(project, RENAME)
    model = RecordingModel(
        replies=[weather_call('lookup_weather'), AIMessage('done'), AIMessage('still done'), AIMessage('done again')]
    )
    agent = build_agent(model, agent_control(label='production', publish_baseline=False), checkpointer=InMemorySaver())
    thread: Any = {'configurable': {'thread_id': 'thread-1'}}
    agent.invoke({'messages': [{'role': 'user', 'content': 'weather in Paris?'}]}, thread)

    republish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'fetch_weather'}]})
    agent.invoke({'messages': [{'role': 'user', 'content': 'and now?'}]}, thread)
    republish(project, {})
    result = agent.invoke({'messages': [{'role': 'user', 'content': 'and now?'}]}, thread)

    # The thread stores one name -- the code's -- so every turn replays the history under whatever
    # the model is being shown *now*, and a thread outlives a change to the rename or its removal.
    assert [tool_call_names(request['messages']) for request in model.requests] == snapshot(
        [[], ['lookup_weather'], ['fetch_weather'], ['get_weather']]
    )
    assert [tool['name'] for tool in bound_tools(model, 3)] == ['get_weather', 'get_time']
    assert tool_call_names(result['messages']) == ['get_weather']


async def test_two_interleaved_runs_read_their_own_replies(project: LocalVariableProvider) -> None:
    """Two runs of one agent, overlapping, where the second advertises different tools than the first.

    The routing a rename needs belongs to the request that advertised it. Kept on the middleware --
    one object every concurrent run of an agent shares -- the second run's tools would decide where
    the first run's reply goes, and a reply naming a tool the other run never advertised has nowhere
    to go at all.
    """
    publish(project, RENAME)
    model = InterleavedModel(entered=asyncio.Event(), released=asyncio.Event())
    agent = build_agent(model, agent_control(label='production'), before=[HideTools('quick')])

    slow = asyncio.create_task(agent.ainvoke({'messages': [{'role': 'user', 'content': 'slow weather?'}]}))
    await model.entered.wait()
    # The overlapping run advertises no tools at all, so the rename reaches nothing on *its* request.
    with pytest.warns(UserWarning, match="patches tool 'get_weather', which no toolset advertises"):
        quick = await agent.ainvoke({'messages': [{'role': 'user', 'content': 'quick hello?'}]})
    model.released.set()
    result = await slow

    assert [message.text for message in quick['messages']] == ['quick hello?', 'nothing to call']
    assert messages(result)[2] == ('tool', 'sunny in Paris', 'get_weather')


def test_a_tool_choice_naming_a_renamed_tool_is_forwarded(project: LocalVariableProvider) -> None:
    publish(project, RENAME)
    model = RecordingModel(replies=[weather_call('lookup_weather'), AIMessage('done')])
    run(build_agent(model, agent_control(label='production'), before=[ForceTool('get_weather')]))

    # The code forced one of its own tools; the model is shown the name that tool is advertised
    # under, because the one the code wrote is not a tool this request offers.
    assert model.requests[0]['kwargs']['tool_choice'] == snapshot(
        {'type': 'function', 'function': {'name': 'lookup_weather'}}
    )


@pytest.mark.parametrize(
    ('choice', 'forwarded'),
    [
        ('get_weather', 'lookup_weather'),
        ('auto', 'auto'),
        ({'type': 'tool', 'name': 'get_weather'}, {'type': 'tool', 'name': 'lookup_weather'}),
        (
            {'type': 'function', 'function': {'name': 'get_time'}},
            {'type': 'function', 'function': {'name': 'get_time'}},
        ),
        ({'type': 'any'}, {'type': 'any'}),
        ({'type': 'function', 'function': {'name': 3}}, {'type': 'function', 'function': {'name': 3}}),
        (None, None),
    ],
)
def test_every_shape_a_tool_choice_takes_is_translated_or_left_alone(choice: Any, forwarded: Any) -> None:
    assert rename_tool_choice(choice, {'get_weather': 'lookup_weather'}) == forwarded


def test_a_call_in_provider_content_blocks_is_translated_too() -> None:
    # Anthropic replays an assistant turn from its content blocks when they carry no matching id, so
    # the name is translated there as well as in the calls LangChain parsed out of them.
    reply = AIMessage(
        content=[{'type': 'tool_use', 'id': 'call-1', 'name': 'get_weather', 'input': {'city': 'Paris'}}],
        tool_calls=[{'name': 'get_weather', 'args': {'city': 'Paris'}, 'id': 'call-1'}],
    )
    plain = AIMessage('nothing to call')
    renamed = rename_tool_calls([plain, reply], {'get_weather': 'lookup_weather'})

    assert renamed[0] is plain
    assert renamed[1].content == snapshot(
        [{'type': 'tool_use', 'id': 'call-1', 'name': 'lookup_weather', 'input': {'city': 'Paris'}}]
    )
    assert tool_call_names(renamed) == ['lookup_weather']


def test_content_that_calls_nothing_renamed_is_the_message_that_came_in() -> None:
    # A reply that carries provider content blocks but calls nothing this config renamed is not
    # rewritten, so a run with a published rename in it still sends on the objects it was given.
    reply = AIMessage(content=[{'type': 'text', 'text': 'Let me think.'}])
    assert rename_tool_calls([reply], {'get_weather': 'lookup_weather'})[0] is reply


def test_an_untouched_tool_is_advertised_as_the_object_the_agent_built(project: LocalVariableProvider) -> None:
    publish(project, {'tool_definitions': [{'name': 'get_weather', 'description': 'Look the weather up.'}]})
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'))
    run(agent)

    assert [tool['description'] for tool in bound_tools(model)] == snapshot(
        ['Look the weather up.', 'Get the current time in a city.']
    )


def test_an_override_that_says_nothing_about_the_description_keeps_the_code_one(
    project: LocalVariableProvider,
) -> None:
    @tool
    def undocumented(city: str) -> str:
        """Say nothing about itself."""
        return f'sunny in {city}'

    weather = cast_tool(undocumented)
    weather.description = ''
    publish(project, {'tool_definitions': [{'name': 'undocumented', 'new_name': 'lookup_weather'}]})
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production'), tools=[weather]))

    assert weather.invoke({'city': 'Paris'}) == 'sunny in Paris'
    # An empty description is a choice the code made, and a rename is not a reason to reopen it.
    assert bound_tools(model)[0] == snapshot(
        {
            'name': 'lookup_weather',
            'description': '',
            'parameters': {'properties': {'city': {'type': 'string'}}, 'required': ['city'], 'type': 'object'},
        }
    )


def test_a_call_the_model_makes_under_a_code_name_is_left_alone(project: LocalVariableProvider) -> None:
    publish(project, RENAME)
    model = RecordingModel(replies=[weather_call('get_time'), AIMessage('done')])
    result = run(build_agent(model, agent_control(label='production')))

    assert messages(result)[2] == ('tool', 'noon in Paris', 'get_time')


def test_a_rename_onto_a_name_another_tool_answers_to_is_dropped(project: LocalVariableProvider) -> None:
    publish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'get_time'}]})
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'))

    with pytest.warns(UserWarning, match="renames 'get_weather' to 'get_time', which is already advertised"):
        run(agent)
    assert [tool['name'] for tool in bound_tools(model)] == ['get_weather', 'get_time']


def test_a_tool_the_agent_does_not_advertise_is_reported(project: LocalVariableProvider) -> None:
    publish(project, {'tool_definitions': [{'name': 'refund', 'description': 'Refund an order.'}]})
    agent = build_agent(RecordingModel(replies=[AIMessage('ok')]), agent_control(label='production'))

    with pytest.warns(UserWarning, match="patches tool 'refund', which no toolset advertises"):
        run(agent)


def test_a_toolset_qualified_override_matches_nothing_here(project: LocalVariableProvider) -> None:
    # LangChain has no notion of a toolset, so no tool reports one -- which is a thing to say out
    # loud rather than a thing to quietly not do.
    publish(project, {'tool_definitions': [{'name': 'get_weather', 'toolset': 'crm', 'description': 'Weather.'}]})
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'))

    with pytest.warns(UserWarning, match="patches tool 'get_weather' from toolset 'crm', which no toolset"):
        run(agent)
    assert bound_tools(model)[0]['description'] == 'Get the current weather for a city.'


def test_a_provider_built_in_is_passed_through(project: LocalVariableProvider) -> None:
    # A `dict` entry is a server-side tool the provider runs itself: there is no code-side
    # implementation to route a rename back to, and nothing in it for the contract to describe.
    built_in: dict[str, Any] = {'type': 'web_search'}
    publish(project, RENAME)
    model = RecordingModel(replies=[AIMessage('ok')])
    tools: list[Any] = [*TOOLS, built_in]
    run(build_agent(model, agent_control(label='production'), tools=tools))

    assert model.requests[0]['kwargs']['tools'][2] == built_in
    assert [tool['name'] for tool in bound_tools(model)[:2]] == ['lookup_weather', 'get_time']


def test_an_unmatched_override_can_fail_the_request_instead(project: LocalVariableProvider) -> None:
    publish(project, {'tool_definitions': [{'name': 'refund', 'description': 'Refund an order.'}]})
    agent = build_agent(
        RecordingModel(replies=[AIMessage('ok')]), agent_control(label='production', on_unmatched='error')
    )

    with pytest.raises(ValueError, match="patches tool 'refund', which no toolset advertises"):
        run(agent)


class HideTools(AgentMiddleware[Any, Any, Any]):
    """A middleware of the user's own, advertising no tools for one kind of request."""

    def __init__(self, marker: str) -> None:
        self.tools = []
        self._marker = marker

    def _request(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        return request.override(tools=[]) if self._marker in request.messages[0].text else request

    async def awrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]
    ) -> ModelResponse[Any]:
        return await handler(self._request(request))


class InterleavedModel(RecordingModel):
    """A model that holds one run's reply until another run has been all the way through."""

    entered: Any = None
    released: Any = None

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        # Answering from the request rather than from a script keeps the reply each run gets
        # independent of the order two overlapping runs happen to reach the model in.
        self.requests.append({'messages': messages, 'kwargs': kwargs})
        if any(isinstance(message, ToolMessage) for message in messages):
            reply = AIMessage('done')
        elif kwargs.get('tools'):
            reply = weather_call('lookup_weather')
        else:
            reply = AIMessage('nothing to call')
        return ChatResult(generations=[ChatGeneration(message=reply)])

    async def _agenerate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        last = messages[-1]
        if isinstance(last, HumanMessage) and 'slow' in last.text:
            self.entered.set()
            await self.released.wait()
        return self._generate(messages, **kwargs)


def cast_tool(value: Any) -> BaseTool:
    """`@tool` returns `BaseTool` but is typed as returning its decorated callable."""
    return value
