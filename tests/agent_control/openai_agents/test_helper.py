"""The helper's own contract: what it refuses, what it names, and how it translates a model string."""

from __future__ import annotations

from typing import Any

import pytest
from agents import Agent, Runner
from agents.retry import ModelRetryAdvice, ModelRetryAdviceRequest
from inline_snapshot import snapshot

from logfire.agent_control.openai_agents import agent_control
from logfire.agent_control.openai_agents._models import to_canonical_model_name, to_sdk_model_name
from logfire.variables.local import LocalVariableProvider

from .conftest import FakeModel, FakeProvider, controlled, publish

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ('canonical', 'sdk'),
    [
        ('openai:gpt-5.6-luna', 'gpt-5.6-luna'),
        ('anthropic:claude-fable-5-1', 'litellm/anthropic/claude-fable-5-1'),
        # The contract splits Google in two and the gateway names both differently.
        ('google:gemini-3-flash', 'litellm/gemini/gemini-3-flash'),
        ('google-cloud:gemini-3-flash', 'litellm/vertex_ai/gemini-3-flash'),
        # The ids Pydantic AI v1 spelled those two with, which a config published then still carries.
        ('google-gla:gemini-3-flash', 'litellm/gemini/gemini-3-flash'),
        ('google-vertex:gemini-3-flash', 'litellm/vertex_ai/gemini-3-flash'),
        # The rest of the providers the two sides spell differently.
        ('fireworks:kimi-k2', 'litellm/fireworks_ai/kimi-k2'),
        ('together:kimi-k2', 'litellm/together_ai/kimi-k2'),
        ('moonshotai:kimi-k2', 'litellm/moonshot/kimi-k2'),
        ('bedrock-mantle:model', 'litellm/bedrock_mantle/model'),
        ('vercel:model', 'litellm/vercel_ai_gateway/model'),
        # A provider the two sides agree on goes to the gateway under the id the contract gave it.
        ('groq:kimi-k2', 'litellm/groq/kimi-k2'),
        ('gpt-5.6-luna', 'gpt-5.6-luna'),
        ('litellm/anthropic/claude-fable-5-1', 'litellm/anthropic/claude-fable-5-1'),
    ],
)
def test_a_canonical_model_string_lowers_into_the_sdk_convention(canonical: str, sdk: str) -> None:
    assert to_sdk_model_name(canonical) == sdk


@pytest.mark.parametrize(
    ('sdk', 'canonical'),
    [
        ('gpt-5.6-luna', 'openai:gpt-5.6-luna'),
        ('openai/gpt-5.6-luna', 'openai:gpt-5.6-luna'),
        ('litellm/anthropic/claude-fable-5-1', 'anthropic:claude-fable-5-1'),
        # Always the current id, never the one v1 spelled it with: nothing writes a legacy id back.
        ('litellm/gemini/gemini-3-flash', 'google:gemini-3-flash'),
        ('litellm/vertex_ai/gemini-3-flash', 'google-cloud:gemini-3-flash'),
        ('litellm/fireworks_ai/kimi-k2', 'fireworks:kimi-k2'),
        ('litellm/together_ai/kimi-k2', 'together:kimi-k2'),
        ('litellm/moonshot/kimi-k2', 'moonshotai:kimi-k2'),
        ('litellm/bedrock_mantle/model', 'bedrock-mantle:model'),
        ('litellm/vercel_ai_gateway/model', 'vercel:model'),
        ('any-llm/mistral/large', 'mistral:large'),
        # Nothing in these names says which provider they are for, so neither does the baseline.
        ('litellm/some-gateway-alias', 'litellm/some-gateway-alias'),
        ('my-registered-prefix/model', 'my-registered-prefix/model'),
    ],
)
def test_an_sdk_model_name_rises_to_the_canonical_form(sdk: str, canonical: str) -> None:
    assert to_canonical_model_name(sdk) == canonical


def test_an_agent_without_a_name_is_refused() -> None:
    with pytest.raises(ValueError, match='needs a name for this agent'):
        agent_control(Agent(name='  '))


def test_a_name_can_be_given_when_the_agents_own_is_not_the_one_to_key_on() -> None:
    agent = agent_control(Agent(name='Checkout Assistant'), name='checkout_assistant')
    assert controlled(agent)._control.variable_name == 'agent__checkout_assistant'  # pyright: ignore[reportPrivateUsage]


def test_blocks_and_the_agents_own_prompt_cannot_both_be_the_prompt() -> None:
    with pytest.raises(ValueError, match='only one of them can be the prompt'):
        agent_control(Agent(name='both', instructions='Hi.'), instructions={'agent': 'Hi.'})


def test_an_empty_mapping_of_blocks_is_refused() -> None:
    with pytest.raises(ValueError, match='empty mapping of `instructions` blocks'):
        agent_control(Agent(name='none'), instructions={})


def test_the_wrapper_describes_itself(project: LocalVariableProvider) -> None:
    agent = agent_control(Agent(name='described', model='gpt-5.6-luna'), label='production')
    assert repr(controlled(agent)) == snapshot(
        "_ControlledModel(AgentControl(name='described', label='production'), code_model='gpt-5.6-luna')"
    )


async def test_lifecycle_calls_reach_the_model_that_answered(project: LocalVariableProvider) -> None:
    """The runner calls these on the model it was given, which is the wrapper, not the one behind it."""
    closed: list[str] = []
    cleaned: list[object] = []
    advice = ModelRetryAdvice(retry_after=1.0)

    class LifecycleModel(FakeModel):
        async def close(self) -> None:
            closed.append(self.label)

        async def _cleanup_on_run_end(self, owner: object) -> None:
            cleaned.append(owner)

        def get_retry_advice(self, request: ModelRetryAdviceRequest) -> ModelRetryAdvice | None:
            return advice

    inner = LifecycleModel('inner')
    agent = agent_control(Agent(name='lifecycle', instructions='Hi.', model='m'), provider=FakeProvider({'m': inner}))
    wrapper = controlled(agent)

    # Before the first request there is no model behind the wrapper to ask.
    assert wrapper.get_retry_advice(_retry_request()) is None
    await wrapper.close()
    await wrapper._cleanup_on_run_end(object())  # pyright: ignore[reportPrivateUsage]
    assert (closed, cleaned) == ([], [])

    await Runner.run(agent, 'hello')
    assert wrapper.get_retry_advice(_retry_request()) is advice
    await wrapper.close()
    assert closed == ['inner']
    # The runner told the wrapper the run had ended, and the wrapper told the model that answered it.
    assert len(cleaned) == 1


def _retry_request() -> ModelRetryAdviceRequest:
    return ModelRetryAdviceRequest(
        error=RuntimeError('boom'), attempt=1, stream=False, previous_response_id=None, conversation_id=None
    )


async def test_a_managed_model_is_resolved_through_the_users_own_provider(
    project: LocalVariableProvider,
) -> None:
    """The adapter translates the name; the provider the user passed is what resolves it."""
    publish(project, 'agent__routed', {'model': 'openai:gpt-5.6-terra'})
    provider = FakeProvider()
    agent = agent_control(Agent(name='routed', instructions='Hi.'), provider=provider)
    await Runner.run(agent, 'hello')

    # The code model -- here the provider's own default -- is resolved once for the baseline as well.
    assert provider.requested == snapshot([None, 'gpt-5.6-terra'])


async def test_an_agent_with_no_model_resolves_the_providers_own_default(
    project: LocalVariableProvider,
) -> None:
    provider = FakeProvider()
    agent: Any = agent_control(Agent(name='defaulted', instructions='Hi.'), provider=provider)
    await Runner.run(agent, 'hello')

    assert provider.requested == snapshot([None])


async def test_a_published_model_this_process_cannot_build_is_reported_and_the_code_model_runs(
    project: LocalVariableProvider,
) -> None:
    """Resolving a model name is a call that can fail, and a published value may not take an agent down."""
    publish(project, 'agent__unbuildable', {'model': 'anthropic:claude-fable-5-1'})

    class Missing(FakeProvider):
        def get_model(self, model_name: str | None) -> Any:
            if model_name is not None and model_name.startswith('litellm/'):
                raise ImportError("The 'litellm' extra is required")
            return super().get_model(model_name)

    code = FakeModel('code')
    agent = agent_control(
        Agent(name='unbuildable', instructions='Hi.', model='m'),
        provider=Missing({'m': code}),
        publish_baseline=False,
    )
    with pytest.warns(UserWarning, match='could not resolve'):
        result = await Runner.run(agent, 'hello')

    assert result.final_output == 'done by code'


async def test_a_published_model_this_process_cannot_build_can_refuse_the_request(
    project: LocalVariableProvider,
) -> None:
    publish(project, 'agent__strict', {'model': 'anthropic:claude-fable-5-1'})

    class Missing(FakeProvider):
        def get_model(self, model_name: str | None) -> Any:
            if model_name is not None and model_name.startswith('litellm/'):
                raise ImportError("The 'litellm' extra is required")
            return super().get_model(model_name)

    agent = agent_control(
        Agent(name='strict', instructions='Hi.', model='m'),
        provider=Missing({'m': FakeModel()}),
        on_unmatched='error',
        publish_baseline=False,
    )
    with pytest.raises(ValueError, match='could not resolve'):
        await Runner.run(agent, 'hello')
