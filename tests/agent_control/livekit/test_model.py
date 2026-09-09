"""Switching models: turning `provider:model` into the object LiveKit runs a turn on."""

from __future__ import annotations

import anthropic as anthropic_sdk
import pytest
from livekit.agents import AgentSession, llm
from livekit.agents.inference import LLM as InferenceLLM
from livekit.plugins import anthropic, google, openai

from logfire.agent_control.livekit._agent import ManagedLLM, effective_llm
from logfire.agent_control.livekit._models import INFERENCE_PROVIDERS, PLUGIN_MODELS, PluginModel, build, canonical_id
from logfire.agent_control.livekit._settings import plugin_for
from logfire.variables.local import LocalVariableProvider

from ..conftest import publish
from .agents import managed, run
from .conftest import clear
from .stubs import StubLLM, StubOpenAILLM

pytestmark = pytest.mark.anyio


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> StubOpenAILLM:
    """The model a published `model` builds to, recording instead of calling OpenAI.

    `build` is what turns `provider:model` into a real plugin object, and it is covered on its own
    above; here the question is whether the agent's turns move onto whatever it returns."""
    model = StubOpenAILLM(model='gpt-5.2')

    def build_stub(model_id: str, code_model: object) -> StubOpenAILLM:
        return model

    monkeypatch.setattr('logfire.agent_control.livekit._agent.build', build_stub)
    return model


def named(model: object) -> str:
    return canonical_id(model, plugin_for(model).name)  # type: ignore[arg-type]


def test_a_model_is_named_by_its_provider_not_its_host() -> None:
    assert named(openai.LLM(model='gpt-4.1')) == 'openai:gpt-4.1'
    assert named(anthropic.LLM(model='claude-sonnet-4-6', client=anthropic_sdk.AsyncClient(api_key='t'))) == (
        'anthropic:claude-sonnet-4-6'
    )
    assert named(google.LLM(model='gemini-2.5-flash')) == 'google:gemini-2.5-flash'
    assert named(InferenceLLM('moonshotai/kimi-k2.6')) == 'moonshotai:kimi-k2.6'
    # Nothing classifies a model from an unknown plugin, so its own id is published untouched.
    assert named(StubLLM(model='mystery-1')) == 'mystery-1'


def test_a_framework_native_id_goes_to_livekit_inference() -> None:
    model = build('openai/gpt-4.1', None)
    assert isinstance(model, InferenceLLM) and model.model == 'openai/gpt-4.1'


def test_an_inference_agent_stays_on_inference() -> None:
    model = build('deepseek:deepseek-v3.2', InferenceLLM('openai/gpt-4.1'))
    assert isinstance(model, InferenceLLM) and model.model == 'deepseek-ai/deepseek-v3.2'


def test_the_same_plugin_keeps_its_client() -> None:
    """Only the model name changes: the base URL, credentials, and HTTP client come along."""
    code_model = openai.LLM(model='gpt-4.1', base_url='https://example.test/v1')
    built = build('openai:gpt-5.2', code_model)
    assert isinstance(built, openai.LLM) and built.model == 'gpt-5.2'
    assert built._client is code_model._client


def test_another_provider_gets_its_own_plugin() -> None:
    built = build('google:gemini-2.5-pro', openai.LLM(model='gpt-4.1'))
    assert isinstance(built, google.LLM) and built.model == 'gemini-2.5-pro'
    # The same plugin, told which of Google's two APIs the canonical provider names.
    assert PLUGIN_MODELS['google-cloud'] == PluginModel('livekit.plugins.google', {'vertexai': True}, False)


def test_the_ids_pydantic_ai_v2_replaced_are_still_accepted() -> None:
    """A config published against a v1-era agent can still carry `google-gla` / `google-vertex`.

    Pydantic AI v2 renamed them to `google` and `google-cloud`, and those are what a baseline
    publishes; the old pair keeps resolving to the same plugin so an old config still applies.
    """
    assert PLUGIN_MODELS['google-gla'] is PLUGIN_MODELS['google']
    assert PLUGIN_MODELS['google-vertex'] is PLUGIN_MODELS['google-cloud']
    assert INFERENCE_PROVIDERS['google-gla'] == INFERENCE_PROVIDERS['google'] == 'google'
    # And Vertex is the one the `vertexai` constructor argument is for, under either id.
    assert PLUGIN_MODELS['google-vertex'].kwargs == {'vertexai': True}
    assert PLUGIN_MODELS['google-gla'].kwargs is None


def test_a_provider_with_no_plugin_falls_back_to_inference() -> None:
    built = build('xai:grok-4.3', openai.LLM(model='gpt-4.1'))
    assert isinstance(built, InferenceLLM) and built.model == 'xai/grok-4.3'


def test_a_plugin_that_is_not_installed_falls_back_to_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(PLUGIN_MODELS, 'openai', PluginModel('livekit.plugins.not_installed'))
    built = build('openai:gpt-4.1', None)
    assert isinstance(built, InferenceLLM) and built.model == 'openai/gpt-4.1'


def test_a_provider_nothing_knows_is_refused() -> None:
    with pytest.raises(ValueError, match="no LiveKit plugin or LiveKit Inference provider is known for 'acme'"):
        build('acme:model-1', None)


async def test_a_published_model_runs_the_turn(project: LocalVariableProvider, published: StubOpenAILLM) -> None:
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.2'})
    agent = managed()()
    code_model = StubOpenAILLM(model='gpt-4.1')
    await run(agent, code_model)
    # The code model never saw the request: the turn ran on the model Logfire named.
    assert code_model.requests == []
    assert len(published.requests) == 1
    assert effective_llm(agent) is published
    # And the boundary in front of it reports the model that actually answered.
    assert isinstance(agent.llm, ManagedLLM)
    assert (agent.llm.model, agent.llm.provider) == (published.model, published.provider)


async def test_removing_the_published_model_puts_the_code_one_back(
    project: LocalVariableProvider, published: StubOpenAILLM
) -> None:
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.2'})
    agent = managed()()
    code_model = StubOpenAILLM(model='gpt-4.1')

    session = AgentSession(llm=code_model)
    await session.start(agent)
    try:
        await session.run(user_input='hi')
        assert code_model.requests == []
        clear(project, 'agent__checkout')
        await session.run(user_input='hi again')
    finally:
        await session.aclose()
    assert len(published.requests) == 1
    assert len(code_model.requests) == 1
    # Nothing is managed any more, so there is no boundary left in front of the model either.
    assert agent.llm is code_model


async def test_an_unchanged_published_model_is_built_once(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.2'})
    swapped = StubOpenAILLM(model='gpt-5.2')
    builds: list[str] = []

    def record(model_id: str, _: object) -> StubOpenAILLM:
        builds.append(model_id)
        return swapped

    monkeypatch.setattr('logfire.agent_control.livekit._agent.build', record)

    session = AgentSession(llm=StubOpenAILLM(model='gpt-4.1'))
    await session.start(managed()())
    try:
        await session.run(user_input='hi')
        await session.run(user_input='hi again')
    finally:
        await session.aclose()
    assert len(swapped.requests) == 2
    assert builds == ['openai:gpt-5.2']


async def test_a_model_that_cannot_be_built_leaves_the_code_one_running(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'model': 'acme:model-1'})
    stub = StubOpenAILLM(model='gpt-4.1')
    with pytest.warns(UserWarning, match="selects model 'acme:model-1', which could not be built"):
        await run(managed()(), stub)
    assert len(stub.requests) == 1


async def test_a_model_the_user_swaps_in_becomes_the_code_one(project: LocalVariableProvider) -> None:
    """`update_options(llm=...)` is a supported mid-session move, and a stale snapshot must not undo it."""
    publish(project, 'agent__checkout', {'instructions': [{'id': 'agent', 'instructions': 'PUBLISHED'}]})
    agent = managed()()
    first = StubOpenAILLM(model='gpt-4.1')
    second = StubOpenAILLM(model='gpt-4.1-mini')

    session = AgentSession(llm=first)
    await session.start(agent)
    try:
        await session.run(user_input='hi')
        agent.update_options(llm=second)
        await session.run(user_input='hi again')
    finally:
        await session.aclose()
    assert len(first.requests) == 1
    assert len(second.requests) == 1
    assert effective_llm(agent) is second


async def test_a_model_the_user_swaps_in_survives_an_unmanaged_turn(project: LocalVariableProvider) -> None:
    """The same, with nothing published: the reconciliation must not put the entry model back."""
    publish(project, 'agent__checkout', {})
    agent = managed()()
    first = StubOpenAILLM(model='gpt-4.1')
    second = StubOpenAILLM(model='gpt-4.1-mini')

    session = AgentSession(llm=first)
    await session.start(agent)
    try:
        await session.run(user_input='hi')
        agent.update_options(llm=second)
        await session.run(user_input='hi again')
    finally:
        await session.aclose()
    assert len(first.requests) == 1
    assert len(second.requests) == 1


async def test_the_boundary_is_transparent_with_no_request_in_flight() -> None:
    """Reached by a node holding on to `agent.llm` outside a turn: the model answers as itself."""
    stub = StubLLM()
    boundary = ManagedLLM(stub)
    errors: list[llm.LLMError] = []
    boundary.on('error', errors.append)

    async with boundary.chat(chat_ctx=llm.ChatContext.empty()) as stream:
        async for _ in stream:
            pass
    assert len(stub.requests) == 1

    # The activity subscribes to the boundary, so what the model says has to come out of it.
    error = llm.LLMError(timestamp=0.0, label='stub', error=RuntimeError('boom'), recoverable=False)
    stub.emit('error', error)
    assert errors == [error]

    await boundary.aclose()
    boundary.detach()
