"""What happens when Logfire has nothing to say, and what a custom node still gets to do."""

from __future__ import annotations

from typing import Any

import pytest
from livekit.agents import Agent, AgentSession, llm
from livekit.agents.types import NOT_GIVEN

from logfire.agent_control.livekit import agent_control
from logfire.agent_control.livekit._agent import effective_llm
from logfire.variables.local import LocalVariableProvider

from ..conftest import publish
from .agents import get_weather, managed, outputs, run
from .stubs import StubLLM, StubOpenAILLM

pytestmark = pytest.mark.anyio


async def test_no_provider_configured_runs_the_agent_as_written() -> None:
    """No `project` fixture: nothing resolves Logfire variables at all, which is local development."""
    stub = StubLLM()
    agent = managed(instructions='CODE PROMPT')()
    await run(agent, stub)
    assert stub.requests[0].system_text == 'CODE PROMPT'
    # Nothing is managed, so nothing was put in front of the model either.
    assert agent.llm is NOT_GIVEN


async def test_an_unreadable_config_runs_the_agent_as_written(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(project, 'agent__checkout', {'instructions': ['ADDED']})

    def boom(*_: Any, **__: Any) -> None:
        raise RuntimeError('logfire is down')

    monkeypatch.setattr(type(project), 'get_variable_config', boom)
    # Publishing the baseline reads the same provider, and its failure is a separate warning.
    stub = StubLLM()
    with pytest.warns(UserWarning, match='Failed to read the Logfire managed config'):
        await run(managed(instructions='CODE PROMPT', publish_baseline=False)(), stub)
    assert stub.requests[0].system_text == 'CODE PROMPT'


async def test_a_config_that_manages_nothing_runs_the_agent_as_written(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {})
    stub = StubLLM()
    await run(managed(instructions='CODE PROMPT')(), stub)
    assert stub.requests[0].system_text == 'CODE PROMPT'


async def test_a_per_call_instruction_outranks_the_published_one(project: LocalVariableProvider) -> None:
    """`generate_reply(instructions=...)` is a per-call value, and LiveKit appends it after the agent's."""
    publish(project, 'agent__checkout', {'instructions': [{'id': 'agent', 'instructions': 'PUBLISHED'}]})
    stub = StubLLM()
    session = AgentSession(llm=stub)
    await session.start(managed(instructions='CODE PROMPT')())
    try:
        await session.generate_reply(instructions='Just say hello.')
    finally:
        await session.aclose()
    assert stub.requests[0].system_texts == ['PUBLISHED', 'Just say hello.']


async def test_the_agents_own_model_outranks_the_sessions() -> None:
    own = StubLLM(model='agent-model')
    agent = managed(model=own)()
    session = AgentSession(llm=StubLLM(model='session-model'))
    await session.start(agent)
    try:
        assert effective_llm(agent) is own
        await session.run(user_input='hi')
    finally:
        await session.aclose()
    assert len(own.requests) == 1


@pytest.mark.parametrize(
    'node',
    [
        pytest.param('generator', id='async generator'),
        pytest.param('coroutine', id='coroutine returning an async iterable'),
        pytest.param('text', id='coroutine returning text'),
        pytest.param('chunk', id='coroutine returning one chunk'),
        pytest.param('nothing', id='coroutine returning nothing'),
    ],
)
async def test_every_shape_of_custom_node_still_runs(project: LocalVariableProvider, node: str) -> None:
    """A node is free to answer without a model at all, in any shape LiveKit takes."""
    publish(project, 'agent__checkout', {'instructions': [{'id': 'agent', 'instructions': 'PUBLISHED'}]})

    async def chunks() -> Any:
        yield llm.ChatChunk(id='c', delta=llm.ChoiceDelta(role='assistant', content='Hi.'))

    @agent_control(name='checkout', label='production')
    class Custom(Agent):
        def __init__(self) -> None:
            super().__init__(instructions='CODE')

        def llm_node(self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: Any) -> Any:
            async def coroutine() -> Any:
                if node == 'coroutine':
                    return chunks()
                if node == 'text':
                    return 'Hi.'
                if node == 'chunk':
                    return llm.ChatChunk(id='c', delta=llm.ChoiceDelta(role='assistant', content='Hi.'))
                return None

            return chunks() if node == 'generator' else coroutine()

    result = await run(Custom(), StubLLM())
    said = [event.item.text_content for event in result.events if event.type == 'message']
    assert said == ([] if node == 'nothing' else ['Hi.'])


async def test_a_custom_node_keeps_running_once_something_is_published(project: LocalVariableProvider) -> None:
    """Publishing a tool description must not take a node's guardrails, retrieval or logging away."""
    publish(
        project,
        'agent__checkout',
        {
            'instructions': [{'id': 'agent', 'instructions': 'PUBLISHED'}],
            'tool_definitions': [{'name': 'get_weather', 'new_name': 'fetch_weather'}],
        },
    )
    seen: list[int] = []

    @agent_control(name='checkout', label='production')
    class Custom(Agent):
        def __init__(self) -> None:
            super().__init__(instructions='CODE', tools=[get_weather])

        async def llm_node(self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: Any) -> Any:
            seen.append(len(chat_ctx.items))
            chat_ctx.add_message(role='user', content='ADDED BY THE NODE')
            async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
                yield chunk

    stub = StubLLM(tool_call='fetch_weather')
    result = await run(Custom(), stub)

    # The node ran on every request of the turn, and what it added reached the model...
    assert len(seen) == 2
    assert stub.requests[0].message_texts[-1] == 'ADDED BY THE NODE'
    # ...alongside everything the published config asked for.
    assert stub.requests[0].system_text == 'PUBLISHED'
    assert stub.requests[0].tool_names == ['fetch_weather']
    assert outputs(result) == [('get_weather', 'weather(get_weather, Paris)')]


async def test_a_nodes_own_request_values_outrank_the_published_ones(project: LocalVariableProvider) -> None:
    """A node computed those for this one request, which the contract puts above a published value."""
    publish(project, 'agent__checkout', {'settings': {'temperature': 0.1, 'parallel_tool_calls': False}})

    @agent_control(name='checkout', label='production')
    class Custom(Agent):
        def __init__(self) -> None:
            super().__init__(instructions='CODE')

        async def llm_node(self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: Any) -> Any:
            model = self.llm
            assert isinstance(model, llm.LLM)
            async with model.chat(
                chat_ctx=chat_ctx, tools=tools, extra_kwargs={'temperature': 0.9}, parallel_tool_calls=True
            ) as stream:
                async for chunk in stream:
                    yield chunk

    stub = StubOpenAILLM(model='gpt-4.1')
    await run(Custom(), stub)
    assert stub.requests[0].extra_kwargs == {'temperature': 0.9}
    assert stub.requests[0].parallel_tool_calls is True
