"""Fixtures: a model that records what it was sent, and the agent every test in here builds.

The Logfire project, and the guards that keep one test's warnings and publishes out of the next,
come from `tests/agent_control/conftest.py`; only what is LangChain-shaped lives here.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Sequence
from typing import Any, cast

import pytest
from langchain.agents import create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, tool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from logfire.agent_control import _control  # pyright: ignore[reportPrivateUsage]
from logfire.agent_control.langchain import AgentControlMiddleware
from logfire.variables import LabeledValue, VariableConfig
from logfire.variables.local import LocalVariableProvider

from ..conftest import publish as publish_variable

AGENT_VARIABLE = 'agent__checkout'
"""The variable every test's agent is keyed on, since every test's agent is called `checkout`."""


@pytest.fixture(autouse=True)
def _join_baseline_publishes(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Join every baseline publish before the next test starts.

    The adapter publishes from the first model request, off the request's thread, and most tests
    here have no reason to wait for it. One still running into the next test is not merely noise: it
    validates pydantic models, and `tests/conftest.py` clears pydantic's plugin cache between tests,
    so the two race over `pydantic.plugin._loader._loading_plugins`.
    """
    threads: list[threading.Thread] = []
    spawn = _control._spawn_baseline_publish  # pyright: ignore[reportPrivateUsage]

    def spawn_and_remember(*args: Any, **kwargs: Any) -> threading.Thread:
        thread = spawn(*args, **kwargs)
        threads.append(thread)
        return thread

    monkeypatch.setattr(_control, '_spawn_baseline_publish', spawn_and_remember)
    yield
    for thread in threads:
        thread.join(timeout=10)


def publish(provider: LocalVariableProvider, value: Any, *, name: str = AGENT_VARIABLE, label: str = 'production'):
    """Put `value` in the project under one label, the shape a project has once someone saved in the UI."""
    return publish_variable(provider, name, value, label=label)


def republish(provider: LocalVariableProvider, value: Any, *, name: str = AGENT_VARIABLE, label: str = 'production'):
    """Save a new version of a value someone already published, the way the UI would."""
    config = provider.get_variable_config(name)
    assert config is not None
    published = config.labels[label].version
    version = (published or 0) + 1
    return provider.update_variable(
        name,
        config.model_copy(
            update={'labels': {label: LabeledValue(version=version, serialized_value=json.dumps(value))}}
        ),
    )


def variable(provider: LocalVariableProvider, name: str = AGENT_VARIABLE) -> VariableConfig:
    """The agent's variable, which the adapter creates by publishing its baseline."""
    config = provider.get_variable_config(name)
    assert config is not None
    return config


def published_baseline(provider: LocalVariableProvider, name: str = AGENT_VARIABLE) -> Any:
    """The baseline the adapter published, parsed back out of the variable's `example`."""
    example = variable(provider, name).example
    assert example is not None
    return json.loads(example)


class RecordingModel(BaseChatModel):
    """A chat model that answers from a script and records every request it was handed.

    Standing in for a provider is the only way to see what a published config did: the assertions in
    this suite are about the request that would have gone out -- its system message, its bound tool
    definitions, and the settings kwargs -- which is exactly what a real integration turns into an
    HTTP body. `test_live.py` is the other half: the same claims, against a real provider.
    """

    provider: str = 'openai'
    model: str = 'fake-1'
    replies: list[AIMessage] = Field(default_factory=list[AIMessage])
    requests: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    temperature: float | None = None
    max_tokens: int | None = None
    reasoning_effort: str | None = None

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        index = len(self.requests)
        self.requests.append({'messages': messages, 'kwargs': kwargs})
        reply = self.replies[min(index, len(self.replies) - 1)]
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: Any | None = None,
        parallel_tool_calls: bool | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        # Named `parallel_tool_calls` because both major integrations do, and the adapter applies
        # that setting only to a model whose `bind_tools` names it.
        return self.bind(
            tools=[convert_to_openai_tool(t) for t in tools],
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            **kwargs,
        )

    def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> Any:
        return {'ls_provider': self.provider, 'ls_model_name': self.model, 'ls_model_type': 'chat'}

    @property
    def _llm_type(self) -> str:
        return 'recording'


def system_message(model: RecordingModel, index: int = 0) -> BaseMessage:
    """The system message the model was sent on its `index`th request."""
    return model.requests[index]['messages'][0]


def bound_tools(model: RecordingModel, index: int = 0) -> list[dict[str, Any]]:
    """The tool definitions the model was shown on its `index`th request, as the provider sees them."""
    return [tool['function'] for tool in model.requests[index]['kwargs']['tools'] if 'function' in tool]


def settings(model: RecordingModel, index: int = 0) -> dict[str, Any]:
    """The settings kwargs the model was called with, minus the tool binding itself."""
    return {
        name: value
        for name, value in model.requests[index]['kwargs'].items()
        if name not in ('tools', 'tool_choice') and value is not None
    }


def declared_prompt(text: str = 'You are a helpful assistant.', block_id: str = 'role') -> SystemMessage:
    """A prompt whose block names itself, which is how code says the text is its own and stays put.

    A `ModelRequest` carries no provenance: text `create_agent` was written with and text a
    `@dynamic_prompt` middleware computed from this run arrive here as the same string. An `id` is
    the declaration, so it is what makes a block static -- publishable with its text, and
    addressable from Logfire.
    """
    return SystemMessage(content=[{'type': 'text', 'text': text, 'id': block_id}])


@tool(parse_docstring=True)
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: The city to look up.
    """
    return f'sunny in {city}'


@tool(parse_docstring=True)
def get_time(city: str) -> str:
    """Get the current time in a city.

    Args:
        city: The city to look up.
    """
    return f'noon in {city}'


TOOLS: list[BaseTool] = [get_weather, get_time]


def weather_call(name: str = 'get_weather', city: str = 'Paris') -> AIMessage:
    """A reply asking for one tool call, so a run reaches the tool node."""
    return AIMessage(content='', tool_calls=[{'name': name, 'args': {'city': city}, 'id': 'call-1'}])


def build_agent(
    model: BaseChatModel,
    control: AgentControlMiddleware,
    *,
    tools: Sequence[BaseTool] | None = None,
    system_prompt: str | SystemMessage | None = 'You are a helpful assistant.',
    name: str | None = 'checkout',
    before: Sequence[Any] = (),
    **kwargs: Any,
) -> Any:
    """The agent every test builds: the Agent Control middleware last, as it has to be."""
    return create_agent(
        model,
        tools=list(TOOLS if tools is None else tools),
        system_prompt=system_prompt,
        name=name,
        middleware=[*before, control],
        **kwargs,
    )


def run(agent: Any, prompt: str = 'weather in Paris?') -> dict[str, Any]:
    return cast('dict[str, Any]', agent.invoke({'messages': [{'role': 'user', 'content': prompt}]}))


def wait_for_publish(middleware: AgentControlMiddleware) -> None:
    """Join the background thread the baseline publish runs on, so the project can be asserted on."""
    control = middleware._control  # pyright: ignore[reportPrivateUsage]
    assert control is not None
    thread = control._publish_thread  # pyright: ignore[reportPrivateUsage]
    if thread is not None:
        thread.join(timeout=10)
