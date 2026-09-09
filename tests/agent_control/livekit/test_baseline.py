"""What the Logfire editor opens on: the agent as written."""

from __future__ import annotations

import json

import pytest
from livekit.agents import AgentSession, llm

from logfire.agent_control.livekit import instruction_blocks
from logfire.variables.local import LocalVariableProvider

from .agents import control_of, get_weather, lookup_order, managed, run
from .stubs import StubOpenAILLM, StubRealtimeModel

pytestmark = pytest.mark.anyio


def published_example(provider: LocalVariableProvider, name: str) -> dict[str, object]:
    config = provider.get_variable_config(name)
    assert config is not None and config.example is not None
    return json.loads(config.example)


async def test_the_baseline_describes_the_agent(project: LocalVariableProvider) -> None:
    agent_cls = managed(
        instructions=instruction_blocks(
            {'agent': 'You are a concise checkout assistant.', 'refunds': 'Confirm the order total.'},
            audio='Keep it short.',
            text='Use markdown.',
        ),
        tools=[get_weather, llm.Toolset(id='orders', tools=[lookup_order])],
    )
    stub = StubOpenAILLM(model='gpt-4.1', temperature=0.2, max_completion_tokens=256, parallel_tool_calls=False)
    await run(agent_cls(), stub)
    control = control_of(agent_cls)
    assert control._publish_thread is not None
    control._publish_thread.join(timeout=5)

    assert published_example(project, 'agent__checkout') == {
        'instructions': [
            {'id': 'agent', 'instructions': 'You are a concise checkout assistant.', 'dynamic': False},
            {'id': 'refunds', 'instructions': 'Confirm the order total.', 'dynamic': False},
            {'id': 'agent:audio', 'instructions': 'Keep it short.', 'dynamic': False},
            {'id': 'agent:text', 'instructions': 'Use markdown.', 'dynamic': False},
        ],
        'model': 'openai:gpt-4.1',
        'settings': {'max_tokens': 256, 'temperature': 0.2, 'parallel_tool_calls': False, 'timeout': 10.0},
        'tool_definitions': [
            {
                'name': 'get_weather',
                'description': 'Get the current weather for a city.\n',
                'parameters': {'city': {'description': 'The city to look up.'}},
            },
            {
                'name': 'lookup_order',
                'description': 'Look up an order.',
                'parameters': {'order_id': {'description': 'Order id.'}},
                'toolset': 'orders',
            },
        ],
    }


async def test_a_runtime_prompt_is_not_published_as_the_code_one(project: LocalVariableProvider) -> None:
    """`update_instructions()` text belongs to one run; the baseline is what the code says."""
    agent_cls = managed(instructions='CODE PROMPT')
    agent = agent_cls()
    session = AgentSession(llm=StubOpenAILLM(model='gpt-4.1'))
    await session.start(agent)
    try:
        await agent.update_instructions('SOMETHING A REQUEST DECIDED')
        await session.run(user_input='hi')
    finally:
        await session.aclose()
    control = control_of(agent_cls)
    assert control._publish_thread is not None
    control._publish_thread.join(timeout=5)

    example = published_example(project, 'agent__checkout')
    assert example['instructions'] == [{'id': 'agent', 'instructions': 'CODE PROMPT', 'dynamic': False}]


async def test_a_realtime_agent_publishes_no_settings_and_no_toolset_tools(
    project: LocalVariableProvider,
) -> None:
    """A realtime session's tools are replaced in place, so only the loose ones can be edited at all."""
    agent_cls = managed(
        'doorbell', instructions='Answer the door.', tools=[get_weather, llm.Toolset(id='orders', tools=[lookup_order])]
    )
    session = AgentSession(llm=StubRealtimeModel())
    await session.start(agent_cls())
    await session.aclose()
    control = control_of(agent_cls)
    assert control._publish_thread is not None
    control._publish_thread.join(timeout=5)

    assert published_example(project, 'agent__doorbell') == {
        'instructions': [{'id': 'agent', 'instructions': 'Answer the door.', 'dynamic': False}],
        'model': 'stub-realtime',
        'tool_definitions': [
            {
                'name': 'get_weather',
                'description': 'Get the current weather for a city.\n',
                'parameters': {'city': {'description': 'The city to look up.'}},
            }
        ],
    }
