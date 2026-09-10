"""The middleware itself: which agent it manages, when it resolves, and what it does with nothing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest
from inline_snapshot import snapshot
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

import logfire
from logfire.agent_control import AgentControl
from logfire.agent_control.langchain import AgentControlMiddleware, AgentControlState, agent_control
from logfire.agent_control.langchain._middleware import STATE_KEY
from logfire.agent_control.langchain._models import build_model, read_model_id, to_langchain_model_id
from logfire.variables.local import LocalVariableProvider

from .conftest import (
    RecordingModel,
    build_agent,
    declared_prompt,
    publish,
    published_baseline,
    run,
    settings,
    system_message,
    variable,
)


def capture(middleware: AgentControlMiddleware, model: RecordingModel, **kwargs: Any) -> ModelRequest[Any]:
    """Run the middleware over one model request and return the request it would have sent."""
    kwargs.setdefault('system_message', None)
    request = ModelRequest(model=model, messages=[], tools=[], **kwargs)
    captured: list[ModelRequest[Any]] = []

    def handler(request: ModelRequest[Any]) -> ModelResponse[Any]:
        captured.append(request)
        return ModelResponse(result=[AIMessage('ok')])

    middleware.wrap_model_call(request, handler)
    return captured[0]


def test_two_overlapping_runs_of_two_names_stay_out_of_each_others_variable(
    project: LocalVariableProvider, wait_for_publish: Callable[[], None]
) -> None:
    # `before_agent` and `wrap_model_call` are different graph nodes, so a second run can start
    # between one run's two halves. Everything the second half needs about the agent has to come
    # from the run's own state: a name kept on the middleware would be whichever run wrote it last,
    # and this run's prompt, model and tools would be published under the other one's variable.
    publish(project, {'instructions': [{'id': 'system:role', 'instructions': 'You are TERSE.'}]})
    publish(project, {'instructions': [{'id': 'system:role', 'instructions': 'You are BRIEF.'}]}, name='agent__other')
    middleware = agent_control(label='production')
    # The two arguments a graph node is handed and this hook does not read; the run's `config`,
    # which carries the name, is the third.
    state, runtime = AgentControlState(messages=[]), cast(Any, None)

    checkout = middleware.before_agent(state, runtime, {'metadata': {'lc_agent_name': 'checkout'}})
    middleware.before_agent(state, runtime, {'metadata': {'lc_agent_name': 'other'}})
    request = capture(middleware, RecordingModel(), state=checkout, system_message=declared_prompt())
    wait_for_publish()

    assert request.system_message is not None and request.system_message.text == 'You are TERSE.'
    assert published_baseline(project)['instructions'] == snapshot(
        [{'id': 'system:role', 'instructions': 'You are a helpful assistant.', 'dynamic': False}]
    )
    assert variable(project, 'agent__other').example is None


def test_it_reports_the_agent_it_manages() -> None:
    assert repr(agent_control(name='checkout', label='production')) == snapshot(
        "AgentControlMiddleware(name='checkout', label='production')"
    )
    assert repr(agent_control()) == snapshot('AgentControlMiddleware(name=None, label=None)')


def test_an_agent_created_without_a_name_says_so(project: LocalVariableProvider) -> None:
    agent = build_agent(RecordingModel(replies=[AIMessage('ok')]), agent_control(), tools=[], name=None)

    with pytest.raises(ValueError, match=r'this agent has none: `create_agent\(\)` was called without `name=`'):
        run(agent)


def test_an_agent_somebody_named_langgraph_is_an_agent_with_a_name(project: LocalVariableProvider) -> None:
    # An agent created without a `name` carries no `lc_agent_name` on the run at all, so the absent
    # key is the signal. `'LangGraph'` reaching this middleware means somebody named it that.
    publish(
        project, {'instructions': [{'id': 'system:role', 'instructions': 'You are TERSE.'}]}, name='agent__langgraph'
    )
    model = RecordingModel(replies=[AIMessage('ok')])
    run(
        build_agent(
            model, agent_control(label='production'), tools=[], name='LangGraph', system_prompt=declared_prompt()
        )
    )

    assert system_message(model).text == 'You are TERSE.'


def test_an_unnamed_agent_can_be_named_on_the_middleware(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': [{'id': 'system:role', 'instructions': 'You are TERSE.'}]})
    model = RecordingModel(replies=[AIMessage('ok')])
    control = agent_control(name='checkout', label='production')
    run(build_agent(model, control, tools=[], name=None, system_prompt=declared_prompt()))

    assert system_message(model).text == 'You are TERSE.'


def test_a_run_that_renames_the_agent_renames_it_for_that_run_only(project: LocalVariableProvider) -> None:
    # LangChain merges a run's own `metadata` over the one `create_agent` bound, so a caller can
    # rename the agent per run -- in Logfire's traces as well, since the LangChain instrumentation
    # names the agent's spans from the same value. The config follows the agent the trace shows, and
    # follows it back: a rename that outlived its run would point every later run at that config.
    publish(project, {'instructions': 'You are TERSE.'}, name='agent__other')
    publish(project, {'instructions': 'You are BRIEF.'})
    model = RecordingModel(replies=[AIMessage('ok'), AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'), tools=[])

    agent.invoke({'messages': [{'role': 'user', 'content': 'hi'}]}, {'metadata': {'lc_agent_name': 'other'}})
    run(agent)

    assert [system_message(model, index).content for index in (0, 1)] == snapshot(
        ['You are TERSE.\n\nYou are a helpful assistant.', 'You are BRIEF.\n\nYou are a helpful assistant.']
    )


def test_an_explicit_name_is_one_no_run_can_move(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': 'You are TERSE.'}, name='agent__other')
    publish(project, {'instructions': 'You are BRIEF.'})
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(name='checkout', label='production'), tools=[])

    agent.invoke({'messages': [{'role': 'user', 'content': 'hi'}]}, {'metadata': {'lc_agent_name': 'other'}})

    assert system_message(model).content == snapshot('You are BRIEF.\n\nYou are a helpful assistant.')


def test_nothing_published_runs_the_agent_exactly_as_written(project: LocalVariableProvider) -> None:
    model = RecordingModel(temperature=0.1, replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'))
    run(agent)

    assert system_message(model).content == 'You are a helpful assistant.'
    assert settings(model) == {}


def test_no_logfire_at_all_runs_the_agent_exactly_as_written() -> None:
    # No `project` fixture: no variables provider is configured, which is the local-development
    # default and the same outcome as a Logfire nobody can reach.
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production')))

    assert system_message(model).content == 'You are a helpful assistant.'


def test_a_provider_that_cannot_be_read_runs_the_agent_as_written(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(project, {'instructions': 'You are TERSE.'})

    def unreachable(name: str) -> None:
        raise RuntimeError('Logfire is down')

    monkeypatch.setattr(project, 'get_variable_config', unreachable)
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production', publish_baseline=False), tools=[])

    with pytest.warns(UserWarning, match='Failed to read the Logfire managed config'):
        run(agent)
    assert system_message(model).content == 'You are a helpful assistant.'


def test_the_config_is_read_once_per_run_and_used_by_every_request_in_it(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(project, {'instructions': [{'id': 'system:role', 'instructions': 'You are TERSE.'}]})
    middleware = agent_control(name='checkout', label='production')
    reads = 0
    resolution = AgentControl.resolution

    def counting_resolution(control: AgentControl) -> Any:
        nonlocal reads
        reads += 1
        return resolution(control)

    monkeypatch.setattr(AgentControl, 'resolution', counting_resolution)
    model = RecordingModel(
        replies=[
            AIMessage(content='', tool_calls=[{'name': 'get_time', 'args': {'city': 'Paris'}, 'id': 'c1'}]),
            AIMessage('done'),
        ]
    )
    run(build_agent(model, middleware, system_prompt=declared_prompt()))

    assert [request['messages'][0].text for request in model.requests] == ['You are TERSE.', 'You are TERSE.']
    assert reads == 1


def test_the_resolved_config_stays_out_of_the_agents_output(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': 'You are TERSE.'})
    result = run(build_agent(RecordingModel(replies=[AIMessage('ok')]), agent_control(label='production')))

    assert STATE_KEY not in result


def test_a_request_that_never_saw_before_agent_resolves_for_itself(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': 'You are TERSE.'})
    middleware = agent_control(name='checkout', label='production')

    request = capture(middleware, RecordingModel())

    assert request.system_message is not None and request.system_message.content == 'You are TERSE.'


def test_a_published_model_replaces_the_code_model_and_takes_its_settings_with_it(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test')
    publish(project, {'model': 'anthropic:claude-sonnet-4-5', 'settings': {'temperature': 0.4}})
    middleware = agent_control(name='checkout', label='production')

    request = capture(middleware, RecordingModel(max_tokens=99, temperature=0.1))

    assert isinstance(request.model, ChatAnthropic)
    assert request.model.model == 'claude-sonnet-4-5'
    # `max_tokens` is the code model's, carried across; `temperature` is the published override.
    assert request.model_settings == snapshot({'max_tokens': 99, 'temperature': 0.4})


def test_a_model_another_middleware_chose_for_this_request_outranks_the_published_one(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The same rule the per-request `model_settings` already follow: a published value replaces what
    # the agent was *built* with, and loses to a choice made for this one request.
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test')
    publish(project, {'model': 'anthropic:claude-sonnet-4-5', 'settings': {'temperature': 0.4}})
    middleware = agent_control(name='checkout', label='production')

    # The agent's own model, which the published one duly replaces.
    first = capture(middleware, RecordingModel())
    # A later request carrying something else: a fallback after an error, a choice made from the
    # run's own state. That is a decision about this request, so the published model steps aside.
    chosen = RecordingModel(provider='openai', model='gpt-5.5-mini')
    with pytest.warns(UserWarning, match="but this request already carries 'openai:gpt-5.5-mini' rather than"):
        second = capture(middleware, chosen)

    assert isinstance(first.model, ChatAnthropic)
    # Only the `model` section stepped aside: the published settings still reached the request.
    assert second.model is chosen
    assert second.model_settings == {'temperature': 0.4}


def test_a_model_that_will_not_say_what_it_is_still_takes_a_published_one(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test')
    publish(project, {'model': 'anthropic:claude-sonnet-4-5'})

    class UnidentifiedModel(RecordingModel):
        def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> Any:
            raise RuntimeError('no tracing params here')

    request = capture(agent_control(name='checkout', label='production'), UnidentifiedModel())

    assert isinstance(request.model, ChatAnthropic)


def test_a_model_langchain_cannot_build_keeps_the_code_model(project: LocalVariableProvider) -> None:
    publish(project, {'model': 'nosuchprovider:some-model'})
    middleware = agent_control(name='checkout', label='production')
    model = RecordingModel()

    with pytest.warns(UserWarning, match="sets model 'nosuchprovider:some-model', which LangChain could not build"):
        request = capture(middleware, model)
    assert request.model is model


@pytest.mark.parametrize(
    ('published', 'langchain'),
    [
        ('anthropic:claude-fable-5-1', 'anthropic:claude-fable-5-1'),
        ('google:gemini-3-pro', 'google_genai:gemini-3-pro'),
        ('google-cloud:gemini-3-pro', 'google_vertexai:gemini-3-pro'),
        ('mistral:mistral-large', 'mistralai:mistral-large'),
        ('azure:gpt-5.5', 'azure_openai:gpt-5.5'),
        ('bedrock:anthropic.claude-sonnet-4-5', 'bedrock_converse:anthropic.claude-sonnet-4-5'),
        # No provider prefix: LangChain infers it, so a LangChain-native id keeps working.
        ('gpt-5.5', 'gpt-5.5'),
    ],
)
def test_the_contracts_provider_ids_are_spelled_langchains_way(published: str, langchain: str) -> None:
    assert to_langchain_model_id(published) == langchain


@pytest.mark.parametrize(
    ('published', 'langchain'),
    [
        ('google-gla:gemini-3-pro', 'google_genai:gemini-3-pro'),
        ('google-vertex:gemini-3-pro', 'google_vertexai:gemini-3-pro'),
    ],
)
def test_the_ids_the_contract_used_to_spell_google_with_still_resolve(published: str, langchain: str) -> None:
    # `google-gla` and `google-vertex` became `google` and `google-cloud`, and a config published
    # against an agent that predates the rename still carries the old spelling.
    assert to_langchain_model_id(published) == langchain


def test_a_baseline_names_google_the_way_the_contract_names_it_today() -> None:
    # The reverse table is built from the current ids alone, so nothing this adapter publishes
    # sends a reader of the project back to a spelling the contract no longer accepts.
    assert read_model_id(RecordingModel(provider='google_genai', model='gemini-3-pro')) == 'google:gemini-3-pro'
    assert (
        read_model_id(RecordingModel(provider='google_vertexai', model='gemini-3-pro')) == 'google-cloud:gemini-3-pro'
    )


def test_a_model_that_will_not_say_what_it_is_has_no_baseline_identifier() -> None:
    class UnidentifiedModel(RecordingModel):
        def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> Any:
            raise RuntimeError('no tracing params here')

    assert read_model_id(UnidentifiedModel()) is None


def test_the_config_survives_a_checkpointer(project: LocalVariableProvider) -> None:
    # The run's config rides in graph state, so with a checkpointer it is written out and read back
    # between steps rather than kept in memory.
    publish(project, {'instructions': [{'id': 'system:role', 'instructions': 'You are TERSE.'}]})
    model = RecordingModel(
        replies=[
            AIMessage(content='', tool_calls=[{'name': 'get_time', 'args': {'city': 'Paris'}, 'id': 'c1'}]),
            AIMessage('done'),
        ]
    )
    agent = build_agent(
        model, agent_control(label='production'), checkpointer=InMemorySaver(), system_prompt=declared_prompt()
    )
    agent.invoke({'messages': [{'role': 'user', 'content': 'time?'}]}, {'configurable': {'thread_id': 'thread-1'}})

    assert [request['messages'][0].text for request in model.requests] == ['You are TERSE.', 'You are TERSE.']


def test_an_unbuildable_model_warns_once_and_returns_nothing() -> None:
    control = AgentControl('checkout')
    with pytest.warns(UserWarning, match='Unable to infer model provider'):
        assert build_model('mystery-model', control) is None
    # Once per process: the config is applied on every request, and this is one thing to say.
    assert build_model('mystery-model', control) is None


async def test_an_async_agent_applies_the_same_config(project: LocalVariableProvider) -> None:
    publish(
        project,
        {
            'instructions': [{'id': 'system:role', 'instructions': 'You are TERSE.'}],
            'settings': {'temperature': 0.4},
            'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup_weather'}],
        },
    )
    model = RecordingModel(
        replies=[
            AIMessage(content='', tool_calls=[{'name': 'lookup_weather', 'args': {'city': 'Paris'}, 'id': 'c1'}]),
            AIMessage('done'),
        ]
    )
    agent = build_agent(model, agent_control(label='production'), system_prompt=declared_prompt())
    result = await agent.ainvoke({'messages': [{'role': 'user', 'content': 'weather?'}]})

    assert system_message(model).text == 'You are TERSE.'
    assert settings(model) == {'temperature': 0.4}
    assert [(message.type, message.text) for message in result['messages']][2] == ('tool', 'sunny in Paris')


def test_every_span_of_a_request_says_which_published_version_produced_it(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': 'You are TERSE.'})
    seen: list[dict[str, object]] = []

    class BaggageModel(RecordingModel):
        def _generate(self, *args: Any, **kwargs: Any) -> Any:
            seen.append(dict(logfire.get_baggage()))
            return super()._generate(*args, **kwargs)

    model = BaggageModel(
        replies=[
            AIMessage(content='', tool_calls=[{'name': 'get_time', 'args': {'city': 'Paris'}, 'id': 'c1'}]),
            AIMessage('done'),
        ]
    )
    run(build_agent(model, agent_control(label='production')))

    assert seen[0] == snapshot(
        {'logfire.variables.agent__checkout': 'production', 'logfire.variables.agent__checkout.version': '1'}
    )


def test_a_tool_call_runs_inside_the_version_that_asked_for_it(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': 'You are TERSE.'})
    seen: list[dict[str, object]] = []

    from langchain_core.tools import tool as make_tool

    @make_tool
    def note_baggage(city: str) -> str:
        """Look something up.

        Args:
            city: The city to look up.
        """
        seen.append(dict(logfire.get_baggage()))
        return 'noted'

    model = RecordingModel(
        replies=[
            AIMessage(content='', tool_calls=[{'name': 'note_baggage', 'args': {'city': 'Paris'}, 'id': 'c1'}]),
            AIMessage('done'),
        ]
    )
    run(build_agent(model, agent_control(label='production'), tools=[note_baggage]))

    assert seen[0] == snapshot(
        {'logfire.variables.agent__checkout': 'production', 'logfire.variables.agent__checkout.version': '1'}
    )
