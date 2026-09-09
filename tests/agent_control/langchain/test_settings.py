"""What a published `settings` section becomes, both as kwargs and as the provider payload they make."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest
from inline_snapshot import snapshot
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from logfire.agent_control import AgentConfig
from logfire.agent_control.langchain import agent_control
from logfire.agent_control.langchain._settings import carry_settings, lower_settings, read_settings
from logfire.variables.local import LocalVariableProvider

from .conftest import RecordingModel, build_agent, publish, run, settings


class FreezeTemperature(AgentMiddleware[Any, Any, Any]):
    """A middleware of the user's own, making a per-call choice for this one request."""

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResponse[Any]:
        return handler(request.override(model_settings={**request.model_settings, 'temperature': 0.0}))


ALL_SETTINGS: dict[str, Any] = {
    'max_tokens': 42,
    'temperature': 0.4,
    'top_p': 0.9,
    'top_k': 5,
    'seed': 7,
    'presence_penalty': 0.1,
    'frequency_penalty': 0.2,
    'parallel_tool_calls': False,
    'timeout': 3.0,
    'stop_sequences': ['END'],
    'thinking': 'low',
}


def lowered(model: BaseChatModel, values: dict[str, Any], *, has_tools: bool = True) -> dict[str, Any]:
    config = AgentConfig.model_validate({'settings': values})
    return lower_settings(model, config, has_tools=has_tools, on_unmatched='ignore')


def openai() -> ChatOpenAI:
    return ChatOpenAI(model='gpt-5.5', api_key=SecretStr('test'))


def anthropic() -> ChatAnthropic:
    return ChatAnthropic(model_name='claude-sonnet-4-5', api_key=SecretStr('test'), timeout=None, stop=None)


def test_every_canonical_setting_openai_has_a_knob_for_reaches_its_payload() -> None:
    model = openai()
    kwargs = lowered(model, ALL_SETTINGS)
    assert kwargs == snapshot(
        {
            'max_tokens': 42,
            'temperature': 0.4,
            'top_p': 0.9,
            'seed': 7,
            'presence_penalty': 0.1,
            'frequency_penalty': 0.2,
            'timeout': 3.0,
            'stop': ['END'],
            'reasoning_effort': 'low',
            'parallel_tool_calls': False,
        }
    )
    # Proof that these are the names the integration takes at call time, not just names it declares:
    # this is the body it would have POSTed, built without a network.
    payload = cast('dict[str, Any]', model._get_request_payload([HumanMessage('hi')], **kwargs))  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
    assert {name: payload[name] for name in kwargs if name in payload} | {
        'max_completion_tokens': payload['max_completion_tokens']
    } == snapshot(
        {
            'temperature': 0.4,
            'top_p': 0.9,
            'seed': 7,
            'presence_penalty': 0.1,
            'frequency_penalty': 0.2,
            'timeout': 3.0,
            'stop': ['END'],
            'reasoning_effort': 'low',
            'parallel_tool_calls': False,
            'max_completion_tokens': 42,
        }
    )


def test_every_canonical_setting_anthropic_has_a_knob_for_reaches_its_payload() -> None:
    model = anthropic()
    kwargs = lowered(model, ALL_SETTINGS)
    assert kwargs == snapshot(
        {
            'max_tokens': 42,
            'temperature': 0.4,
            'top_p': 0.9,
            'top_k': 5,
            'timeout': 3.0,
            'stop': ['END'],
            'reasoning_effort': 'low',
            'parallel_tool_calls': False,
        }
    )
    payload = cast('dict[str, Any]', model._get_request_payload([HumanMessage('hi')], **kwargs))  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
    assert payload | {'messages': None} == snapshot(
        {
            'model': 'claude-sonnet-4-5',
            'max_tokens': 42,
            'messages': None,
            'stop_sequences': ['END'],
            'timeout': 3.0,
            'parallel_tool_calls': False,
            'output_config': {'effort': 'low'},
            # The integration's own routing for sampling parameters on this model generation.
            'extra_body': {'top_p': 0.9, 'top_k': 5, 'temperature': 0.4},
        }
    )


def test_a_setting_this_model_has_no_knob_for_is_reported(project: LocalVariableProvider) -> None:
    publish(project, {'settings': {'top_k': 5, 'temperature': 0.4}})
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'), tools=[])

    with pytest.warns(UserWarning, match="sets 'top_k', which this agent framework has no equivalent for"):
        run(agent)
    assert settings(model) == {'temperature': 0.4}


def test_thinking_applies_as_an_effort_level_and_is_reported_as_a_switch() -> None:
    model = openai()
    assert lowered(model, {'thinking': 'high'}) == {'reasoning_effort': 'high'}
    with pytest.warns(UserWarning, match="sets 'thinking', which this agent framework has no equivalent for"):
        assert (
            lower_settings(
                model, AgentConfig.model_validate({'settings': {'thinking': True}}), has_tools=True, on_unmatched='warn'
            )
            == {}
        )


def test_parallel_tool_calls_needs_tools_to_be_parallel_over() -> None:
    # With no tools `create_agent` calls `bind()`, which sends the key straight to the provider,
    # where a request with no tools and a `parallel_tool_calls` is an error.
    model = openai()
    assert lowered(model, {'parallel_tool_calls': True}) == {'parallel_tool_calls': True}
    assert lowered(model, {'parallel_tool_calls': True}, has_tools=False) == {}


def test_a_model_whose_bind_tools_does_not_name_it_never_gets_it() -> None:
    class NoParallelTools(RecordingModel):
        def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
            return self.bind(tools=tools, **kwargs)

    model = NoParallelTools()
    assert model.bind_tools([]) is not None
    assert lowered(model, {'parallel_tool_calls': True}) == {}


def test_the_settings_the_agent_was_built_with_are_read_back_canonically() -> None:
    # Spelled with the integration's own aliases, which is the shape its constructor advertises.
    model = ChatOpenAI(
        model='gpt-4.1',
        api_key=SecretStr('test'),
        temperature=0.1,
        max_completion_tokens=1024,
        timeout=30,
        stop_sequences=['END'],
    )
    assert read_settings(model) == snapshot(
        {'max_tokens': 1024, 'temperature': 0.1, 'stop_sequences': ['END'], 'timeout': 30.0}
    )


def test_a_published_model_carries_the_code_models_settings_across() -> None:
    code = ChatAnthropic(
        model_name='claude-sonnet-4-5', api_key=SecretStr('test'), temperature=0.1, top_k=5, timeout=None, stop=None
    )
    # `top_k` does not move: OpenAI has no such knob, so it was never a thing that model could do.
    assert carry_settings(code, openai()) == snapshot({'max_tokens': 64000, 'temperature': 0.1})


def test_a_per_call_setting_from_another_middleware_outranks_the_published_one(
    project: LocalVariableProvider,
) -> None:
    publish(project, {'settings': {'temperature': 0.4, 'max_tokens': 42}})
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'), tools=[], before=[FreezeTemperature()])
    run(agent)

    assert settings(model) == snapshot({'max_tokens': 42, 'temperature': 0.0})


def test_a_setting_the_model_class_does_not_declare_is_not_read_back() -> None:
    # `RecordingModel` declares three of the eleven; the rest are not its to have.
    assert read_settings(RecordingModel(max_tokens=99, temperature=0.5)) == {'max_tokens': 99, 'temperature': 0.5}
