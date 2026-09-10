"""Switching the model, including to one served by a different class than the code model's."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models import LlmCapabilities
from google.adk.models.base_llm_connection import BaseLlmConnection
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.models.registry import LLMRegistry
from inline_snapshot import snapshot

import logfire
from logfire.agent_control.google_adk import agent_control
from logfire.agent_control.google_adk._model import (
    _ADK_PREFIX_PROVIDERS,
    _PROVIDER_PREFIXES,
    ManagedLlm,
    to_adk_model_name,
    to_canonical_model_name,
)
from logfire.testing import CaptureLogfire
from logfire.variables.local import LocalVariableProvider

from .conftest import REGISTERED_REQUESTS, Conversation, FakeLlm, fake_llm, publish, run

pytestmark = pytest.mark.anyio


class LegacyFakeLlm(FakeLlm):
    """A model whose ADK name keeps the `:` a canonical name uses as its provider separator."""

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r'legacy:.*']


LLMRegistry.register(LegacyFakeLlm)


@pytest.fixture(autouse=True)
def _forget_registered_requests() -> None:  # pyright: ignore[reportUnusedFunction]
    REGISTERED_REQUESTS.clear()


@pytest.mark.parametrize(
    ('canonical', 'adk'),
    [
        ('google:gemini-2.5-flash', 'gemini-2.5-flash'),
        ('google-cloud:gemini-2.5-flash', 'gemini-2.5-flash'),
        # The two ids Pydantic AI v1 spelled the Google providers with, which a config published
        # against a v1-era agent still carries. v2 renamed both, so they are input-only.
        ('google-gla:gemini-2.5-flash', 'gemini-2.5-flash'),
        ('google-vertex:gemini-2.5-flash', 'gemini-2.5-flash'),
        ('anthropic:claude-fable-5-1', 'claude-fable-5-1'),
        ('openai:gpt-5.6-sol', 'openai/gpt-5.6-sol'),
        ('groq:llama-3.3-70b', 'groq/llama-3.3-70b'),
        # No provider at all: a framework-native name, which the contract says to pass through.
        ('gemini-2.5-flash', 'gemini-2.5-flash'),
    ],
)
def test_a_canonical_name_becomes_the_one_adk_routes(canonical: str, adk: str) -> None:
    assert to_adk_model_name(canonical) == adk


@pytest.mark.parametrize(
    ('adk', 'canonical'),
    [
        ('gemini-2.5-flash', 'google:gemini-2.5-flash'),
        ('gemma-3-27b-it', 'google:gemma-3-27b-it'),
        ('claude-fable-5-1', 'anthropic:claude-fable-5-1'),
        ('gpt-5.6-sol', 'openai:gpt-5.6-sol'),
        ('openai/gpt-5.6-sol', 'openai:gpt-5.6-sol'),
        # Nothing classifies it, so the baseline says what the code says and guesses at nothing.
        ('fake-code-model', 'fake-code-model'),
    ],
)
def test_an_adk_name_is_described_as_the_contract_would(adk: str, canonical: str) -> None:
    assert to_canonical_model_name(adk) == canonical


def test_no_baseline_names_a_provider_pydantic_ai_has_retired() -> None:
    """Every id the baseline can emit is one the current contract resolves; the legacy ones are input-only.

    `google-gla` and `google-vertex` were removed in Pydantic AI v2 in favour of `google` and
    `google-cloud`. Emitting one into a baseline would put a value in the editor that nothing
    downstream can resolve, so the two tables are deliberately asymmetric and this says so.
    """
    assert set(_ADK_PREFIX_PROVIDERS.values()) == snapshot({'google', 'anthropic', 'openai'})
    assert set(_ADK_PREFIX_PROVIDERS.values()) <= set(_PROVIDER_PREFIXES)
    assert {'google-gla', 'google-vertex'} <= set(_PROVIDER_PREFIXES)
    assert not {'google-gla', 'google-vertex'} & set(_ADK_PREFIX_PROVIDERS.values())


async def test_a_published_model_serves_the_request(project: LocalVariableProvider) -> None:
    """The class changes, not just the name: ADK chose the code model before this hook ran."""
    publish(project, {'model': 'managed-fake:v2'})
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm), label='production')
    assert await run(agent) == snapshot(['done via managed-fake/v2'])
    assert llm.requests == []
    assert [request.model for request in REGISTERED_REQUESTS] == snapshot(['managed-fake/v2'])


async def test_a_published_name_the_code_model_answers_to_stays_on_it(project: LocalVariableProvider) -> None:
    publish(project, {'model': 'fake-code-model'})
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm), label='production')
    assert await run(agent) == snapshot(['done via fake-code-model'])


async def test_a_name_the_translation_gets_wrong_is_tried_as_published(project: LocalVariableProvider) -> None:
    """`legacy:v9` is an ADK name, not a canonical one, and translating it finds nothing."""
    publish(project, {'model': 'legacy:v9'})
    agent = agent_control(LlmAgent(name='checkout', model=fake_llm()), label='production')
    assert await run(agent) == snapshot(['done via legacy:v9'])


async def test_a_model_adk_cannot_route_leaves_the_agent_on_its_own(project: LocalVariableProvider) -> None:
    publish(project, {'model': 'nowhere:v1'})
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm), label='production')
    with pytest.warns(UserWarning, match="selects model 'nowhere:v1', which Google ADK cannot resolve"):
        assert await run(agent) == snapshot(['done via fake-code-model'])


async def test_an_agent_that_inherits_its_model_says_so(project: LocalVariableProvider) -> None:
    """Resolving an inherited model at wrapping time would pin whatever the tree said then."""
    publish(project, {'model': 'managed-fake:v2'}, name='agent__child')
    child = LlmAgent(name='child')
    LlmAgent(name='parent', model=fake_llm(), sub_agents=[child])
    agent = agent_control(child, label='production')
    with pytest.warns(UserWarning, match='inherits its model from its parent'):
        assert await run(agent) == snapshot(['done via fake-code-model'])


class ConnectingLlm(FakeLlm):
    """A model with a live connection and a declared capability, to show both are forwarded."""

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=True)

    def connect(self, llm_request: LlmRequest) -> AbstractAsyncContextManager[BaseLlmConnection]:
        @asynccontextmanager
        async def connection() -> AsyncGenerator[BaseLlmConnection, None]:
            yield BaseLlmConnection()

        return connection()


async def test_a_switch_to_a_less_capable_model_is_reported(project: LocalVariableProvider) -> None:
    """ADK shapes a request from the agent's own model, and that decision is older than this hook."""
    publish(project, {'model': 'managed-fake:v2'})

    class CapableLlm(FakeLlm):
        @property
        def capabilities(self) -> LlmCapabilities:
            return LlmCapabilities(output_schema_and_tools=True)

    agent = agent_control(
        LlmAgent(name='checkout', model=CapableLlm(model='fake-code-model', script=[], requests=[])),
        label='production',
    )
    with pytest.warns(UserWarning, match='reports different capabilities than'):
        assert await run(agent) == snapshot(['done via managed-fake/v2'])


async def test_a_published_model_is_resolved_once_and_reused(project: LocalVariableProvider) -> None:
    """Every request re-reads the config, and the class it names is built the first time only."""
    publish(project, {'model': 'managed-fake:v2'})
    agent = agent_control(LlmAgent(name='checkout', model=fake_llm()), label='production')
    conversation = Conversation(agent)
    try:
        assert await conversation.turn() == snapshot(['done via managed-fake/v2'])
        assert await conversation.turn() == snapshot(['done via managed-fake/v2'])
    finally:
        await conversation.close()
    assert len(REGISTERED_REQUESTS) == 2
    resolved = agent.canonical_model
    assert isinstance(resolved, ManagedLlm)
    assert list(resolved._resolved) == snapshot(['managed-fake/v2'])


async def test_the_model_call_says_which_published_version_produced_it(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    """ADK opens its `call_llm` span before any hook runs, so the model call re-enters the resolution."""
    publish(project, {'settings': {'temperature': 0.4}})

    class ReportingLlm(FakeLlm):
        """A model that logs from inside the model call, which is where the attribution has to reach."""

        async def generate_content_async(
            self, llm_request: LlmRequest, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            logfire.info('sending the request')
            async for response in super().generate_content_async(llm_request, stream=stream):
                yield response

    agent = agent_control(
        LlmAgent(name='checkout', model=ReportingLlm(model='fake-code-model', script=[], requests=[])),
        label='production',
    )
    await run(agent)
    logged = [span for span in capfire.exporter.exported_spans_as_dict() if span['name'] == 'sending the request']
    assert [span['attributes']['logfire.variables.agent__checkout'] for span in logged] == snapshot(['production'])
    assert [span['attributes']['logfire.variables.agent__checkout.version'] for span in logged] == snapshot(['1'])


async def test_wrapping_a_model_narrows_nothing_about_it() -> None:
    """A wrapper that reported less than the model it wraps would change the agent by wrapping it."""
    code_model = ConnectingLlm(model='fake-code-model')
    managed = ManagedLlm(model=code_model.model, code_model=code_model, current_resolution=lambda: None)
    assert managed.capabilities == code_model.capabilities
    async with managed.connect(LlmRequest()) as connection:
        assert isinstance(connection, BaseLlmConnection)
