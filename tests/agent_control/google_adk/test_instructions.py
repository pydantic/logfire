"""Swapping one block out of a prompt ADK has already joined into a single string."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import Any

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.llm_request import LlmRequest
from google.adk.planners.plan_re_act_planner import PlanReActPlanner
from google.genai import types
from inline_snapshot import snapshot

from logfire.agent_control import Block
from logfire.agent_control.google_adk import _instructions, agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import FakeLlm, fake_llm, publish, run, system_instruction

pytestmark = pytest.mark.anyio

CODE_INSTRUCTION = 'You are a concise checkout assistant.'
IDENTITY = 'You are an agent. Your internal name is "checkout".'


def managed(project: LocalVariableProvider, value: Any, **agent_kwargs: Any) -> tuple[LlmAgent, FakeLlm]:
    """An agent whose config is already published, and the model that records what it was asked."""
    publish(project, value)
    llm = fake_llm()
    agent = agent_control(
        LlmAgent(name='checkout', model=llm, instruction=CODE_INSTRUCTION, **agent_kwargs),
        label='production',
    )
    return agent, llm


async def test_nothing_published_sends_the_prompt_the_code_assembles(project: LocalVariableProvider) -> None:
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, instruction=CODE_INSTRUCTION), label='production')
    await run(agent)
    assert system_instruction(llm.requests[0]) == snapshot("""\
You are a concise checkout assistant.

You are an agent. Your internal name is "checkout".\
""")


async def test_a_published_block_replaces_the_one_the_agent_wrote(project: LocalVariableProvider) -> None:
    agent, llm = managed(project, {'instructions': [{'id': 'agent', 'instructions': 'You are a refund specialist.'}]})
    await run(agent)
    assert system_instruction(llm.requests[0]) == snapshot("""\
You are a refund specialist.

You are an agent. Your internal name is "checkout".\
""")


async def test_the_identity_line_adk_writes_is_a_block_like_any_other(project: LocalVariableProvider) -> None:
    agent, llm = managed(project, {'instructions': [{'id': 'identity', 'instructions': 'You are Ada.'}]})
    await run(agent)
    assert system_instruction(llm.requests[0]) == snapshot("""\
You are a concise checkout assistant.

You are Ada.\
""")


async def test_a_published_block_with_no_text_drops_it(project: LocalVariableProvider) -> None:
    agent, llm = managed(project, {'instructions': [{'id': 'identity'}]})
    await run(agent)
    assert system_instruction(llm.requests[0]) == snapshot('You are a concise checkout assistant.')


async def test_an_added_block_lands_inside_the_cacheable_prefix(project: LocalVariableProvider) -> None:
    """Ahead of the planner's per-request text, which is what keeps published text in a cached prefix."""
    agent, llm = managed(
        project,
        {'instructions': ['Escalate anything over $500 to a human.']},
        planner=PlanReActPlanner(),
    )
    await run(agent)
    prompt = system_instruction(llm.requests[0])
    assert prompt.startswith(f'{CODE_INSTRUCTION}\n\n{IDENTITY}\n\nEscalate anything over $500 to a human.')
    assert prompt.index('Escalate anything') < prompt.index('When answering the question')


async def test_a_static_instruction_is_its_own_block(project: LocalVariableProvider) -> None:
    """ADK routes the agent instruction into user content when a static one is set, so only it is here."""
    publish(project, {'instructions': [{'id': 'static', 'instructions': 'Managed cacheable prefix.'}]})
    llm = fake_llm()
    agent = agent_control(
        LlmAgent(
            name='checkout',
            model=llm,
            static_instruction=types.Content(parts=[types.Part(text='Code cacheable prefix.')]),
            instruction=CODE_INSTRUCTION,
        ),
        label='production',
    )
    await run(agent)
    assert system_instruction(llm.requests[0]) == snapshot("""\
Managed cacheable prefix.

You are an agent. Your internal name is "checkout".\
""")


async def test_a_templated_block_keeps_what_the_code_computes(project: LocalVariableProvider) -> None:
    """It is located, so the partition stays right, and refused, so no rendering is pinned forever."""
    publish(project, {'instructions': [{'id': 'agent', 'instructions': 'Managed.'}]})
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, instruction='Serving {tenant}.'), label='production')
    with pytest.warns(UserWarning, match="addresses instruction block 'agent', which the agent recomputes"):
        await run(agent, state={'tenant': 'acme'})
    assert system_instruction(llm.requests[0]) == snapshot("""\
Serving acme.

You are an agent. Your internal name is "checkout".\
""")


async def test_an_id_this_agent_does_not_assemble_is_reported(project: LocalVariableProvider) -> None:
    agent, llm = managed(project, {'instructions': [{'id': 'global', 'instructions': 'Nowhere.'}]})
    with pytest.warns(UserWarning, match="addresses instruction block 'global', which this request does not"):
        await run(agent)
    assert system_instruction(llm.requests[0]) == snapshot("""\
You are a concise checkout assistant.

You are an agent. Your internal name is "checkout".\
""")


async def test_an_id_this_agent_does_not_assemble_can_stop_the_request(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': [{'id': 'global', 'instructions': 'Nowhere.'}]})
    agent = agent_control(
        LlmAgent(name='checkout', model=fake_llm(), instruction=CODE_INSTRUCTION),
        label='production',
        on_unmatched='error',
    )
    with pytest.raises(ValueError, match="addresses instruction block 'global'"):
        await run(agent)


async def test_a_prompt_that_is_not_text_is_reported_rather_than_rewritten(project: LocalVariableProvider) -> None:
    """A callback ahead of the model can leave a `Content` where the joined string was."""
    publish(project, {'instructions': [{'id': 'agent', 'instructions': 'Managed.'}]})
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, instruction=CODE_INSTRUCTION), label='production')

    def replace_prompt(callback_context: CallbackContext, llm_request: LlmRequest) -> None:
        llm_request.config.system_instruction = types.Content(parts=[types.Part(text='Not a string.')])

    # Ahead of the managed callback, which is where a plugin's callback also runs.
    agent.before_model_callback = [replace_prompt, *agent.canonical_before_model_callbacks]
    with pytest.warns(UserWarning, match='carries a system instruction that is not text'):
        await run(agent)
    assert llm.requests[0].config.system_instruction == types.Content(parts=[types.Part(text='Not a string.')])


@pytest.fixture
async def context(project: LocalVariableProvider) -> CallbackContext:
    """A real `CallbackContext` from a real run, for the source-reading this hook does with one."""
    captured: list[CallbackContext] = []
    agent = LlmAgent(name='checkout', model=fake_llm(), instruction=CODE_INSTRUCTION)
    agent.before_model_callback = lambda callback_context, llm_request: captured.append(callback_context)
    await run(agent)
    return captured[0]


async def test_a_rendering_this_adapter_cannot_reproduce_leaves_the_block_alone(
    context: CallbackContext,
) -> None:
    """`inject_session_state` raising here means only that the seam is lost, never that the run is."""
    agent = LlmAgent(name='other', instruction='Serving {nowhere}.')
    assert await _instructions.agent_sources(agent, context) == snapshot(
        [
            Block(text='', id='agent', dynamic=True),
            Block(text='You are an agent. Your internal name is "other".', id='identity'),
        ]
    )


async def test_a_single_turn_agent_assembles_no_identity_block(context: CallbackContext) -> None:
    """ADK leaves the line out for a single-turn agent, so there is no block to offer."""
    agent = LlmAgent(name='other', instruction='Code.')
    object.__setattr__(agent, 'mode', 'single_turn')
    assert await _instructions.agent_sources(agent, context) == snapshot([Block(text='Code.', id='agent')])


def test_a_static_instruction_this_adapter_cannot_read_is_unlocatable() -> None:
    """Anything but plain text is a reference ADK moves into the request's contents, not a block."""
    assert _instructions._content_text('Plain text is the whole of it.') == 'Plain text is the whole of it.'
    assert _instructions._content_text(types.Part(inline_data=types.Blob(data=b'x', mime_type='image/png'))) == ''
    assert _instructions._content_text([types.Part(text='one'), 'two']) == ''
    assert _instructions._content_text(types.File(name='f')) == ''
    assert _instructions._content_text([types.Part(text='one'), types.Part(text='two')]) == 'one\n\ntwo'


def test_a_source_the_prompt_does_not_contain_is_left_out() -> None:
    """The agent's own callback rewrote the prompt before this one saw it: nothing to address."""
    sources = [Block(text='Missing.', id='agent'), Block(text='Present.', id='identity')]
    assert _instructions.partition('Present.', sources) == snapshot([Block(text='Present.', id='identity')])


def test_a_source_that_also_appears_inside_other_text_is_matched_where_it_was_appended() -> None:
    """A block is addressed by the seams ADK joined it on, not by the first place its text occurs."""
    sources = [Block(text='Be concise.', id='agent')]
    prompt = 'A planner line quoting "Be concise." back at the model.\n\nBe concise.\n\nAnd a tool line after it.'
    assert _instructions.partition(prompt, sources) == snapshot(
        [
            Block(text='A planner line quoting "Be concise." back at the model.', dynamic=True),
            Block(text='Be concise.', id='agent'),
            Block(text='And a tool line after it.', dynamic=True),
        ]
    )


async def test_replacing_a_block_leaves_text_that_merely_contains_it_alone(project: LocalVariableProvider) -> None:
    """The end of the same story: a published block rewrites its own text and nobody else's."""
    publish(project, {'instructions': [{'id': 'identity', 'instructions': 'You are Ada.'}]})
    llm = fake_llm()
    # The agent's own instruction contains the identity line ADK goes on to append below it.
    agent = agent_control(
        LlmAgent(name='checkout', model=llm, instruction=f'Never say: {IDENTITY}'), label='production'
    )
    await run(agent)
    assert system_instruction(llm.requests[0]) == snapshot("""\
Never say: You are an agent. Your internal name is "checkout".

You are Ada.\
""")


async def test_a_config_that_publishes_no_instructions_leaves_the_prompt_untouched(
    project: LocalVariableProvider,
) -> None:
    """Not merely equal text: the object ADK assembled, which no re-join of a partition can be."""
    publish(project, {'settings': {'temperature': 0.4}})
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, instruction=CODE_INSTRUCTION), label='production')
    assembled: list[str] = []

    def remember(callback_context: CallbackContext, llm_request: LlmRequest) -> None:
        assert isinstance(llm_request.config.system_instruction, str)
        assembled.append(llm_request.config.system_instruction)

    agent.before_model_callback = [remember, *agent.canonical_before_model_callbacks]
    await run(agent)
    assert llm.requests[0].config.system_instruction is assembled[0]


async def test_a_prompt_that_is_not_text_is_only_reported_when_instructions_were_published(
    project: LocalVariableProvider,
) -> None:
    """The rest of the config still applies: only the instructions had nowhere to go."""
    publish(project, {'settings': {'temperature': 0.4}})
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, instruction=CODE_INSTRUCTION), label='production')

    def replace_prompt(callback_context: CallbackContext, llm_request: LlmRequest) -> None:
        llm_request.config.system_instruction = types.Content(parts=[types.Part(text='Not a string.')])

    agent.before_model_callback = [replace_prompt, *agent.canonical_before_model_callbacks]
    await run(agent)
    assert llm.requests[0].config.temperature == 0.4
