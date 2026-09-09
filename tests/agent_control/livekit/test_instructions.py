"""The prompt: where its seams are, and what a published value does to them."""

from __future__ import annotations

import pytest
from livekit.agents import AgentSession, llm
from livekit.agents.voice.generation import INSTRUCTIONS_MESSAGE_ID

from logfire.agent_control.livekit import instruction_blocks
from logfire.agent_control.livekit._agent import install_instructions, turn_modality
from logfire.variables.local import LocalVariableProvider

from ..conftest import publish
from .agents import managed, run
from .stubs import StubLLM

pytestmark = pytest.mark.anyio


async def test_one_prompt_is_keyed_agent(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'instructions': [{'id': 'agent', 'instructions': 'PUBLISHED'}]})
    stub = StubLLM()
    await run(managed(instructions='CODE PROMPT')(), stub)
    assert stub.requests[0].system_text == 'PUBLISHED'


async def test_declared_blocks_are_addressed_one_at_a_time(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'instructions': [{'id': 'refunds', 'instructions': 'REWRITTEN'}, 'ADDED']})
    stub = StubLLM()
    await run(managed(instructions=instruction_blocks({'agent': 'FIRST', 'refunds': 'SECOND'}))(), stub)
    assert stub.requests[0].system_text == 'FIRST\n\nREWRITTEN\n\nADDED'


async def test_a_block_with_no_text_is_removed(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'instructions': [{'id': 'refunds'}]})
    stub = StubLLM()
    await run(managed(instructions=instruction_blocks({'agent': 'FIRST', 'refunds': 'SECOND'}))(), stub)
    assert stub.requests[0].system_text == 'FIRST'


async def test_the_turns_modality_variant_is_what_is_addressed(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'instructions': [{'id': 'agent:text', 'instructions': 'MARKDOWN'}]})
    stub = StubLLM()
    instructions = instruction_blocks({'agent': 'FIRST'}, audio='SPEAK BRIEFLY', text='USE MARKDOWN')
    # `AgentSession.run(user_input=...)` is a text turn, so the text variant is the one being sent.
    await run(managed(instructions=instructions)(), stub)
    assert stub.requests[0].system_text == 'FIRST\n\nMARKDOWN'


async def test_the_audio_variant_is_what_a_call_would_send() -> None:
    """A turn with no speech behind it renders the way `update_instructions` does: audio."""
    agent = managed(instructions='CODE')()
    session = AgentSession(llm=StubLLM())
    await session.start(agent)
    try:
        assert session.current_speech is None
        assert turn_modality(agent) == 'audio'
    finally:
        await session.aclose()


async def test_a_runtime_replacement_drops_the_declared_seams(project: LocalVariableProvider) -> None:
    """`update_instructions()` replaces the whole prompt, so the blocks it was assembled from are gone."""
    publish(
        project,
        'agent__checkout',
        {'instructions': [{'id': 'refunds', 'instructions': 'REWRITTEN'}, {'id': 'agent', 'instructions': 'REPLACED'}]},
    )
    agent = managed(instructions=instruction_blocks({'agent': 'FIRST', 'refunds': 'SECOND'}))()
    session = AgentSession(llm=(stub := StubLLM()))
    await session.start(agent)
    try:
        await agent.update_instructions('SOMETHING ELSE ENTIRELY')
        with pytest.warns(UserWarning, match="instruction block 'refunds', which this request does not assemble"):
            await session.run(user_input='hi')
    finally:
        await session.aclose()
    assert stub.requests[0].system_text == 'REPLACED'


async def test_the_stored_history_keeps_the_code_prompt(project: LocalVariableProvider) -> None:
    """The turn's context is a shallow copy of the agent's, so the managed text must not leak into it."""
    publish(project, 'agent__checkout', {'instructions': [{'id': 'agent', 'instructions': 'PUBLISHED'}]})
    agent = managed(instructions='CODE PROMPT')()
    stub = StubLLM()
    await run(agent, stub)
    assert stub.requests[0].system_text == 'PUBLISHED'
    stored = agent.chat_ctx.get_by_id(INSTRUCTIONS_MESSAGE_ID)
    assert isinstance(stored, llm.ChatMessage) and stored.text_content == 'CODE PROMPT'
    assert agent.instructions == 'CODE PROMPT'


async def test_an_id_nothing_carries_is_reported(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'instructions': [{'id': 'nonsense', 'instructions': 'X'}]})
    with pytest.warns(UserWarning, match="instruction block 'nonsense', which this request does not assemble"):
        await run(managed()(), StubLLM())


async def test_an_id_nothing_carries_can_fail_the_request(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'instructions': [{'id': 'nonsense', 'instructions': 'X'}]})
    with pytest.raises(ValueError, match="instruction block 'nonsense'"):
        await run(managed(on_unmatched='error')(), StubLLM())


def test_instructions_are_added_when_the_request_carries_none() -> None:
    """A context with no instruction message gets one, at the front, inside the cacheable prefix.

    LiveKit puts one there for every request it builds itself; this is what keeps a published prompt
    reaching the model when something upstream -- a custom node, a hand-built context -- has not.
    """
    chat_ctx = llm.ChatContext.empty()
    chat_ctx.add_message(role='user', content='hi')
    install_instructions(chat_ctx, 'PUBLISHED')
    added = chat_ctx.items[0]
    assert isinstance(added, llm.ChatMessage)
    assert added.id == INSTRUCTIONS_MESSAGE_ID
    assert added.text_content == 'PUBLISHED'
