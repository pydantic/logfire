"""Fixtures for the OpenAI Agents SDK adapter tests: a fake model, a fake provider, and helpers.

The Logfire project itself, and the guards that make a process say a thing once, come from the core's
own conftest one directory up: the adapter is tested against the same project fixture the core is.
"""

from __future__ import annotations

import json
import threading
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any, cast

import pytest
from agents import Agent, ModelSettings, Tool, function_tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseOutputItem, TResponseStreamEvent
from agents.models.interface import Model, ModelProvider, ModelTracing
from agents.models.openai_responses import OpenAIResponsesModel
from agents.usage import Usage
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionToolCall,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
)
from openai.types.responses.response_prompt_param import ResponsePromptParam

from logfire.agent_control.openai_agents._adapter import _ControlledModel  # pyright: ignore[reportPrivateUsage]
from logfire.variables.local import LocalVariableProvider

from ..conftest import publish as publish


@pytest.fixture(autouse=True)
def _sdk_default_model(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """Run these tests against the SDK's own default model, whatever the process environment says.

    `OPENAI_DEFAULT_MODEL` decides both which model an agent that names none runs on and -- through
    `Agent.__post_init__`, which compares the agent's settings to the default model's -- whether an
    agent that names one gets that model's implied reasoning settings. Another test module in this
    repository sets it at import time, so leaving it alone would make a baseline here depend on which
    other tests shared the worker.
    """
    monkeypatch.delenv('OPENAI_DEFAULT_MODEL', raising=False)


@pytest.fixture(autouse=True)
def _join_baseline_publishes() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Wait out the background baseline publish before the next test looks at process-wide state.

    `AgentControl.publish_baseline` does its provider round trip on a thread of its own, and a test
    that only asserts on what reached the model never joins it. Left running, that thread builds
    pydantic models while the *next* test's fixtures are asserting on pydantic's plugin-loading flag,
    which is a global -- so the suite fails in a test that has nothing to do with this one.
    """
    before = set(threading.enumerate())
    yield
    for thread in set(threading.enumerate()) - before:
        thread.join(timeout=10)


def published_example(provider: LocalVariableProvider, name: str) -> Any:
    """The baseline the adapter published for `name`, as the JSON the Logfire editor renders."""
    config = provider.get_variable_config(name)
    assert config is not None and config.example is not None
    return json.loads(config.example)


@function_tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: City to look up.
    """
    return f'sunny in {city}'


def text_output(text: str = 'done') -> ResponseOutputMessage:
    """A final assistant message, which is how a turn ends without calling anything."""
    return ResponseOutputMessage(
        id='msg-1',
        type='message',
        role='assistant',
        status='completed',
        content=[ResponseOutputText(type='output_text', text=text, annotations=[])],
    )


def tool_call(name: str, arguments: str = '{"city": "Paris"}', call_id: str = 'call-1') -> ResponseFunctionToolCall:
    """A tool call under the name the model was shown."""
    return ResponseFunctionToolCall(type='function_call', call_id=call_id, name=name, arguments=arguments)


class Recorded:
    """What one model request carried, as the model behind the adapter saw it."""

    def __init__(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: Sequence[Tool],
    ) -> None:
        self.system_instructions = system_instructions
        self.input = input
        self.model_settings = model_settings
        self.tools = list(tools)

    @property
    def tool_names(self) -> list[str]:
        return [tool.name for tool in self.tools]

    @property
    def history_calls(self) -> list[str]:
        items = self.input if isinstance(self.input, list) else []
        return [
            name
            for item in items
            if (entry := cast('dict[str, Any]', item)).get('type') == 'function_call'
            and isinstance(name := entry.get('name'), str)
        ]

    def tool(self, name: str) -> Any:
        return next(tool for tool in self.tools if tool.name == name)


class FakeModel(Model):
    """A model that records every request and replays a scripted response, streamed or not.

    The point of the tests is what reaches the model, so this is the assertion surface: everything a
    published config did shows up in `calls`, and everything the runner did with the response shows
    up in the run result.
    """

    def __init__(self, label: str = 'fake', *, outputs: Sequence[Sequence[TResponseOutputItem]] = ()) -> None:
        self.label = label
        self.calls: list[Recorded] = []
        self.outputs = [list(output) for output in outputs]

    def _next_output(self) -> list[TResponseOutputItem]:
        if self.outputs:
            return self.outputs.pop(0)
        return [text_output(f'done by {self.label}')]

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        self.calls.append(Recorded(system_instructions, input, model_settings, tools))
        return ModelResponse(output=self._next_output(), usage=Usage(), response_id=None)

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        self.calls.append(Recorded(system_instructions, input, model_settings, tools))
        output = self._next_output()
        response = Response(
            id='resp-1',
            created_at=0.0,
            model='fake',
            object='response',
            output=output,
            parallel_tool_calls=False,
            tool_choice='auto',
            tools=[],
            status='completed',
        )
        for index, item in enumerate(output):
            yield ResponseOutputItemAddedEvent(
                type='response.output_item.added', item=item, output_index=index, sequence_number=index
            )
            # An event that carries an item id rather than a name, so nothing about it is renamed.
            yield ResponseFunctionCallArgumentsDeltaEvent(
                type='response.function_call_arguments.delta',
                delta='',
                item_id='item-1',
                output_index=index,
                sequence_number=index,
            )
            yield ResponseOutputItemDoneEvent(
                type='response.output_item.done', item=item, output_index=index, sequence_number=index
            )
        yield ResponseCompletedEvent(type='response.completed', response=response, sequence_number=len(output))


class FakeProvider(ModelProvider):
    """Resolves model names to `FakeModel`s, recording every name it was asked for."""

    def __init__(self, models: dict[str | None, FakeModel] | None = None) -> None:
        self.models = models if models is not None else {}
        self.requested: list[str | None] = []

    def get_model(self, model_name: str | None) -> Model:
        self.requested.append(model_name)
        return self.models.setdefault(model_name, FakeModel(str(model_name)))


def controlled(agent: Agent[Any]) -> _ControlledModel:
    """The wrapper `agent_control` installed on an agent, for a test that asserts on its internals."""
    model = agent.model
    assert isinstance(model, _ControlledModel)
    return model


def wait_for_baseline(agent: Agent[Any]) -> None:
    """Wait out the background thread that publishes the baseline, so a test can read what it wrote."""
    thread = controlled(agent)._control._publish_thread  # pyright: ignore[reportPrivateUsage]
    if thread is not None:
        thread.join()


class FakeResponsesModel(FakeModel, OpenAIResponsesModel):  # pyright: ignore[reportIncompatibleMethodOverride]
    """A fake the adapter recognizes as the Responses model, with no OpenAI client behind it.

    Which settings can be applied depends on the model class, because the Responses API has no
    request field for the two penalties, so a test of that needs a model of that type and nothing
    else about it. The two bases spell the same signature differently, which pyright reads as a
    conflict and which nothing here depends on: `FakeModel` comes first, so `FakeModel` answers.
    """
