"""What a published `settings` section becomes, both as kwargs and as the provider payload they make."""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import Any, cast

import pytest
from inline_snapshot import snapshot
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import Field, SecretStr

from logfire.agent_control import AgentConfig, merge_settings
from logfire.agent_control.langchain import agent_control
from logfire.agent_control.langchain._settings import (
    align_run_settings,
    canonical_name,
    carry_settings,
    lower_settings,
    read_settings,
)
from logfire.variables.local import LocalVariableProvider

from .conftest import RecordingModel, build_agent, publish, run, settings


class FreezeTemperature(AgentMiddleware[Any, Any, Any]):
    """A middleware of the user's own, making a per-call choice for this one request."""

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResponse[Any]:
        return handler(request.override(model_settings={**request.model_settings, 'temperature': 0.0}))


class FreezeStopSequences(AgentMiddleware[Any, Any, Any]):
    """A middleware reaching for the *other* spelling of a setting the published section also sets."""

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResponse[Any]:
        return handler(request.override(model_settings={**request.model_settings, 'stop_sequences': ['FROM THE RUN']}))


class AliasedStopModel(RecordingModel):
    """A model declaring `stop` under an alias, the way both major integrations declare this one."""

    stop: list[str] | None = Field(default=None, alias='stop_sequences')


class ChangingTemperature(AgentMiddleware[Any, Any, Any]):
    """A middleware whose per-call choice is different on every request, as a real one's would be."""

    def __init__(self) -> None:
        self.tools = []
        self.calls = 0

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResponse[Any]:
        self.calls += 1
        return handler(request.override(model_settings={**request.model_settings, 'temperature': self.calls / 10}))


class FreezeParallelToolCalls(AgentMiddleware[Any, Any, Any]):
    """The same, for the one canonical setting that is a `bind_tools()` parameter."""

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResponse[Any]:
        return handler(request.override(model_settings={**request.model_settings, 'parallel_tool_calls': True}))


class FreezeReasoning(AgentMiddleware[Any, Any, Any]):
    """The same, for a setting the integration spells its own way."""

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResponse[Any]:
        return handler(request.override(model_settings={**request.model_settings, 'reasoning_effort': 'high'}))


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

    # It outranks it, and it says so: a published value overridden on every request is one someone
    # can change in Logfire to no effect, with nothing else to say why. `max_tokens`, which nothing
    # chose for this request, is not reported and does apply.
    with pytest.warns(UserWarning, match="sets 'temperature', but this request already carries a `model_settings`"):
        run(agent)

    assert settings(model) == snapshot({'max_tokens': 42, 'temperature': 0.0})


def test_a_per_call_setting_is_reported_once_however_often_its_value_changes(
    project: LocalVariableProvider,
) -> None:
    # The report is deduplicated on its text for the life of the process, so naming the value it
    # lost to would warn on every request instead of once -- and keep every one of those strings.
    publish(project, {'settings': {'temperature': 0.4}})
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'), tools=[], before=[ChangingTemperature()])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        run(agent)
        run(agent)
        run(agent)

    assert [str(warning.message) for warning in caught] == snapshot(
        [
            "Managed agent config sets 'temperature', but this request already carries a `model_settings` value "
            'for it that something chose for this one request, which outranks a published default; that setting '
            'is not applied.'
        ]
    )
    assert settings(model, 2) == snapshot({'temperature': 0.3})


def test_the_integrations_own_spelling_is_reported_as_the_setting_someone_published(
    project: LocalVariableProvider,
) -> None:
    # `thinking` reaches an integration as `reasoning_effort`, so a message naming only the kwarg
    # would send someone hunting the Logfire editor for a setting by a name it does not have.
    publish(project, {'settings': {'thinking': 'low'}})
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'), tools=[], before=[FreezeReasoning()])

    with pytest.warns(UserWarning, match="sets 'thinking', but this request already carries"):
        run(agent)

    assert settings(model) == snapshot({'reasoning_effort': 'high'})


def test_a_bind_tools_parameter_is_reported_under_the_name_it_already_has(
    project: LocalVariableProvider,
) -> None:
    # `parallel_tool_calls` is a `bind_tools()` parameter rather than a model field, so it never goes
    # through the table that translates the contract's names into an integration's own.
    publish(project, {'settings': {'parallel_tool_calls': False}})
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'), before=[FreezeParallelToolCalls()])

    with pytest.warns(UserWarning, match="sets 'parallel_tool_calls', but this request already carries"):
        run(agent)

    assert settings(model) == snapshot({'parallel_tool_calls': True})


@pytest.mark.parametrize(
    ('model', 'sent'),
    [
        # OpenAI declares `stop` and takes `stop_sequences` as its alias; Anthropic the other way
        # round. Either way the published value and the run's are one setting under two spellings.
        (openai, 'stop'),
        (anthropic, 'stop_sequences'),
    ],
    ids=['openai', 'anthropic'],
)
def test_a_run_spelling_a_published_setting_the_other_way_still_overrides_it(
    # `Any`, because the assertion is on the body the integration builds, and `_get_request_payload`
    # is each integration's own rather than something `BaseChatModel` declares.
    model: Callable[[], Any],
    sent: str,
) -> None:
    built = model()
    published = lowered(built, {'stop_sequences': ['PUBLISHED']})
    run_settings = align_run_settings(built, {canonical_name(built, 'stop'): ['FROM THE RUN']}, published)
    merged = merge_settings({}, published, run_settings)

    # One key, the run's value, and a collision the caller can be told about. Left unaligned both
    # keys survive, and on OpenAI that puts `stop_sequences` in the body beside `stop`, where it is
    # not a parameter of the API at all.
    assert merged.settings == snapshot({'stop': ['FROM THE RUN']})
    assert merged.source('stop') == 'run'
    payload = cast('dict[str, Any]', built._get_request_payload([HumanMessage('hi')], **merged.settings))
    assert {name: value for name, value in payload.items() if 'stop' in name} == {sent: ['FROM THE RUN']}


def test_a_run_setting_nothing_published_touches_is_left_spelled_as_it_was() -> None:
    # Aligning only ever moves a key the published section also sets, so a request with nothing
    # published for that setting still carries exactly what the middleware ahead of this one wrote.
    built = openai()
    assert align_run_settings(built, {'stop_sequences': ['A'], 'temperature': 0.5}, {'temperature': 0.1}) == snapshot(
        {'stop_sequences': ['A'], 'temperature': 0.5}
    )


def test_a_run_that_spells_a_published_setting_the_other_way_reaches_the_model_once(
    project: LocalVariableProvider,
) -> None:
    # The end of the same story, through the agent: one key reaches the model, carrying the run's
    # value, and the published one it displaced is reported rather than silently sent alongside.
    publish(project, {'settings': {'stop_sequences': ['PUBLISHED']}})
    model = AliasedStopModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'), tools=[], before=[FreezeStopSequences()])

    with pytest.warns(UserWarning, match="sets 'stop_sequences', but this request already carries"):
        run(agent)

    assert settings(model) == snapshot({'stop': ['FROM THE RUN']})


def test_a_setting_the_model_class_does_not_declare_is_not_read_back() -> None:
    # `RecordingModel` declares three of the eleven; the rest are not its to have.
    assert read_settings(RecordingModel(max_tokens=99, temperature=0.5)) == {'max_tokens': 99, 'temperature': 0.5}
