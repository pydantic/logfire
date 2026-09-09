"""Wiring one agent up: what wins, what is said out loud, and what happens when Logfire is not there."""

from __future__ import annotations

import warnings
from typing import Any

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from inline_snapshot import snapshot

from logfire.agent_control.google_adk import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import baseline, fake_llm, publish, run, system_instruction

pytestmark = pytest.mark.anyio


async def test_a_value_this_run_passes_beats_the_published_one(project: LocalVariableProvider) -> None:
    """The agent's own callbacks run after the managed one, which is what settles precedence."""
    publish(project, {'settings': {'temperature': 0.4}, 'instructions': [{'id': 'agent', 'instructions': 'Managed.'}]})
    llm = fake_llm()

    def this_run(callback_context: CallbackContext, llm_request: LlmRequest) -> None:
        llm_request.config.temperature = 0.9

    agent = agent_control(
        LlmAgent(name='checkout', model=llm, instruction='Code.', before_model_callback=this_run),
        label='production',
    )
    await run(agent)
    assert llm.requests[0].config.temperature == 0.9
    # And what the run said nothing about is still the published value.
    assert system_instruction(llm.requests[0]).startswith('Managed.')


async def test_an_agent_with_callbacks_already_keeps_all_of_them(project: LocalVariableProvider) -> None:
    order: list[str] = []
    llm = fake_llm()
    agent = agent_control(
        LlmAgent(
            name='checkout',
            model=llm,
            before_model_callback=[
                lambda callback_context, llm_request: order.append('first'),
                lambda callback_context, llm_request: order.append('second'),
            ],
        ),
        label='production',
    )
    await run(agent)
    assert order == snapshot(['first', 'second'])


async def test_logfire_being_unreachable_runs_the_agent_on_its_code(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionError('logfire-api.pydantic.dev is unreachable')

    monkeypatch.setattr(project, 'get_serialized_value', unreachable)
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, instruction='Code.'), label='production')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        assert await run(agent) == snapshot(['done via fake-code-model'])
    assert any('agent__checkout' in str(warning.message) for warning in caught)
    assert system_instruction(llm.requests[0]).startswith('Code.')


async def test_no_logfire_project_at_all_runs_the_agent_on_its_code() -> None:
    """The local-development default: nothing configured, nothing published, nothing to apply."""
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, instruction='Code.'), label='production')
    assert await run(agent) == snapshot(['done via fake-code-model'])
    assert system_instruction(llm.requests[0]).startswith('Code.')


async def test_the_config_can_be_keyed_on_a_name_of_its_own(project: LocalVariableProvider) -> None:
    """One config for several agents that share a job, or a key that outlives an ADK rename."""
    publish(project, {'instructions': [{'id': 'agent', 'instructions': 'Managed.'}]}, name='agent__shared')
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, instruction='Code.'), label='production', name='shared')
    await run(agent)
    assert system_instruction(llm.requests[0]).startswith('Managed.')


async def test_publishing_the_baseline_can_be_turned_off(project: LocalVariableProvider) -> None:
    """For a deployment whose variables token is deliberately read-only."""
    publish(project, {})
    llm = fake_llm()
    agent = agent_control(
        LlmAgent(name='checkout', model=llm, instruction='Code.'), label='production', publish_baseline=False
    )
    await run(agent)
    config = project.get_variable_config('agent__checkout')
    assert config is not None and config.example is None


async def test_a_deployment_can_choose_to_hear_nothing(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': [{'id': 'global', 'instructions': 'Nowhere.'}]})
    llm = fake_llm()
    agent = agent_control(
        LlmAgent(name='checkout', model=llm, instruction='Code.'), label='production', on_unmatched='ignore'
    )
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        await run(agent)


async def test_the_agent_handed_back_is_the_one_that_went_in(project: LocalVariableProvider) -> None:
    """Wired up in place, unlike the OpenAI Agents adapter's clone: every reference to it is managed."""
    agent = LlmAgent(name='checkout', model=fake_llm(), instruction='Code.')
    parent = LlmAgent(name='parent', sub_agents=[agent])
    assert agent_control(agent, label='production') is agent
    assert parent.sub_agents[0] is agent


async def test_a_response_from_a_request_this_task_did_not_build_is_left_alone(
    project: LocalVariableProvider,
) -> None:
    """The routing an after-model hook translates by is its own request's, or there is none to use."""
    captured: list[CallbackContext] = []
    other = LlmAgent(name='other', model=fake_llm())
    other.before_model_callback = lambda callback_context, llm_request: captured.append(callback_context)
    await run(other)

    publish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup_weather'}]})
    agent = agent_control(LlmAgent(name='checkout', model=fake_llm()), label='production')
    after_model = agent.canonical_after_model_callbacks[0]
    response = LlmResponse(
        content=types.Content(role='model', parts=[types.Part.from_function_call(name='lookup_weather', args={})])
    )
    after_model(callback_context=captured[0], llm_response=response)  # pyright: ignore[reportCallIssue]
    assert response.content is not None and response.content.parts is not None
    call = response.content.parts[0].function_call
    assert call is not None and call.name == snapshot('lookup_weather')


async def test_an_agent_with_no_name_is_refused() -> None:
    """ADK requires one and validates it as an identifier, so this is the shape that can still slip."""
    with pytest.raises(ValueError, match='has nothing a variable key can be made of'):
        agent_control(LlmAgent(name='checkout', model=fake_llm()), name='  ')


async def test_the_baseline_reaches_a_project_that_has_the_variable_already(
    project: LocalVariableProvider,
) -> None:
    """Someone saved a value in the UI first, so the code side is an update rather than a creation."""
    publish(project, {'settings': {'temperature': 0.4}})
    agent = agent_control(LlmAgent(name='checkout', model=fake_llm(), instruction='Code.'), label='production')
    await run(agent)
    assert await baseline(project) == snapshot("""\
{
  "instructions": [
    {
      "id": "agent",
      "instructions": "Code.",
      "dynamic": false
    },
    {
      "id": "identity",
      "instructions": "You are an agent. Your internal name is \\"checkout\\".",
      "dynamic": false
    }
  ],
  "model": "fake-code-model"
}\
""")
