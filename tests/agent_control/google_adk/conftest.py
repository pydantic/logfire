"""A model that answers without a network, and a way to run one turn of a real ADK `Runner`."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncGenerator, Iterator, Sequence
from typing import Any

import pytest
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.models.registry import LLMRegistry
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from logfire.agent_control._control import BASELINE_PUBLISH_THREAD_PREFIX
from logfire.variables import LabeledValue, Rollout, VariableConfig
from logfire.variables.local import LocalVariableProvider


@pytest.fixture(autouse=True)
def _wait_for_baseline_publishers() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Let a baseline publish finish before the next test inspects process-wide state.

    Unlike the core, this adapter has nowhere to hand the publishing thread back: it publishes from
    inside a per-request hook, and nothing in an agent should be waiting on it. That leaves a test
    that does not poll for the result free to end while the thread is still building Pydantic models,
    and `tests/conftest.py` asserts on `pydantic.plugin._loader._loading_plugins` at every test's
    setup -- so a publisher caught mid-flight fails the *next* test instead of this one.
    """
    yield
    for thread in threading.enumerate():
        if thread.name.startswith(BASELINE_PUBLISH_THREAD_PREFIX):
            thread.join(timeout=10)


def publish(provider: LocalVariableProvider, value: Any, *, name: str = 'agent__checkout', label: str = 'production'):
    """Put `value` in the project under one label, the shape a project has once someone saved in the UI."""
    return provider.create_variable(
        VariableConfig(
            name=name,
            labels={label: LabeledValue(version=1, serialized_value=json.dumps(value))},
            rollout=Rollout(labels={label: 1.0}),
            overrides=[],
        )
    )


def republish(
    provider: LocalVariableProvider,
    value: Any,
    *,
    name: str = 'agent__checkout',
    label: str = 'production',
    version: int = 2,
):
    """Save a new version of a value that is already there, the way editing it in the UI does."""
    config = provider.get_variable_config(name)
    assert config is not None
    return provider.update_variable(
        name,
        config.model_copy(
            update={'labels': {label: LabeledValue(version=version, serialized_value=json.dumps(value))}}
        ),
    )


async def baseline(provider: LocalVariableProvider, name: str = 'agent__checkout') -> str | None:
    """The published code baseline, once the background thread that writes it has caught up.

    The publish deliberately runs off the request's thread so it can never delay or fail a request,
    which leaves a test asking for it before it exists. Polling is the honest wait: the adapter does
    not hand out the thread, because nothing in an agent should be waiting on it.
    """
    for _ in range(200):
        config = provider.get_variable_config(name)
        if config is not None and config.example is not None:
            return config.example
        await asyncio.sleep(0.01)  # pragma: no cover - the write usually lands before the first check
    return None  # pragma: no cover - a publish that never lands is a failure the caller asserts on


class FakeLlm(BaseLlm):
    """A model that records what it was asked and replies from a script, without a network.

    Each scripted turn is either a tool name to call with `{'city': 'Paris'}`, or `None` for a text
    reply naming the model that produced it -- which is how a test tells a managed model switch from
    a request that stayed on the code model.
    """

    script: list[str | None] = []
    requests: list[LlmRequest] = []

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        turn = self.script[len(self.requests) - 1] if len(self.requests) <= len(self.script) else None
        part = (
            types.Part.from_text(text=f'done via {self.model}')
            if turn is None
            else types.Part.from_function_call(name=turn, args={'city': 'Paris'})
        )
        yield LlmResponse(content=types.Content(role='model', parts=[part]))


class RegisteredFakeLlm(FakeLlm):
    """A fake model ADK's own `LLMRegistry` routes a name to, which is what a provider switch does."""

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r'managed-fake/.*']

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        REGISTERED_REQUESTS.append(llm_request)
        async for response in super().generate_content_async(llm_request, stream=stream):
            yield response


REGISTERED_REQUESTS: list[LlmRequest] = []
"""What the registry-built model was asked, which no test can reach through the instance itself."""

LLMRegistry.register(RegisteredFakeLlm)


def fake_llm(model: str = 'fake-code-model', script: Sequence[str | None] = ()) -> FakeLlm:
    """A `FakeLlm` with its own recording lists, since a shared default would leak between tests."""
    return FakeLlm(model=model, script=list(script), requests=[])


class Conversation:
    """One ADK session, run a turn at a time, so a later turn sees what an earlier one persisted."""

    def __init__(self, agent: LlmAgent, state: dict[str, Any] | None = None) -> None:
        self._sessions = InMemorySessionService()
        self._runner = Runner(app_name='app', agent=agent, session_service=self._sessions)
        self._state = state
        self._session_id: str | None = None

    async def turn(self, message: str = 'weather in Paris?') -> list[str]:
        """Run one turn, returning the text the agent produced."""
        if self._session_id is None:
            session = await self._sessions.create_session(app_name='app', user_id='u', state=self._state)
            self._session_id = session.id
        content = types.Content(role='user', parts=[types.Part.from_text(text=message)])
        return [
            part.text
            async for event in self._runner.run_async(user_id='u', session_id=self._session_id, new_message=content)
            for part in (event.content.parts or [] if event.content else [])
            if part.text
        ]

    async def tool_names(self) -> list[str]:
        """Every tool name the session has persisted, in the calls and the responses alike."""
        assert self._session_id is not None
        session = await self._sessions.get_session(app_name='app', user_id='u', session_id=self._session_id)
        assert session is not None
        return [
            (part.function_call or part.function_response).name or ''  # pyright: ignore[reportOptionalMemberAccess]
            for event in session.events
            for part in (event.content.parts or [] if event.content else [])
            if part.function_call or part.function_response
        ]

    async def close(self) -> None:
        # What a real deployment does when it is done with a runner, and what closes the toolsets.
        await self._runner.close()


async def run(agent: LlmAgent, message: str = 'weather in Paris?', state: dict[str, Any] | None = None) -> list[str]:
    """Run one turn of `agent` through a real ADK `Runner`, returning the text it produced."""
    conversation = Conversation(agent, state=state)
    try:
        return await conversation.turn(message)
    finally:
        await conversation.close()


def system_instruction(request: LlmRequest) -> str:
    """The prompt one recorded request carried, as the model was shown it."""
    assert isinstance(request.config.system_instruction, str)
    return request.config.system_instruction


def declarations(request: LlmRequest) -> list[types.FunctionDeclaration]:
    """The tool declarations one recorded request carried."""
    return [
        declaration
        for tool in request.config.tools or []
        if isinstance(tool, types.Tool)
        for declaration in tool.function_declarations or []
    ]
