"""Model settings: what each plugin has a knob for, and what happens to the rest."""

from __future__ import annotations

from collections.abc import Callable

import anthropic as anthropic_sdk
import pytest
from livekit.agents.inference import LLM as InferenceLLM
from livekit.agents.types import NOT_GIVEN
from livekit.plugins import google

from logfire.agent_control.livekit._settings import carry_settings, code_settings, lower, plugin_for
from logfire.variables.local import LocalVariableProvider

from ..conftest import publish
from .agents import managed, run
from .stubs import StubAnthropicLLM, StubLLM, StubOpenAILLM

pytestmark = pytest.mark.anyio

ALL_SETTINGS = {
    'max_tokens': 512,
    'temperature': 0.3,
    'top_p': 0.9,
    'top_k': 40,
    'seed': 7,
    'presence_penalty': 0.1,
    'frequency_penalty': 0.2,
    'parallel_tool_calls': False,
    'timeout': 4.5,
    'stop_sequences': ['END'],
    'thinking': 'high',
}


def build_stub(model: StubOpenAILLM) -> Callable[..., StubOpenAILLM]:
    """A `build` that returns `model` for whatever a published `model` names."""

    def build(model_id: str, code_model: object) -> StubOpenAILLM:
        return model

    return build


def anthropic_llm(**kwargs: object) -> StubAnthropicLLM:
    # The plugin cannot build its own client against this `anthropic` SDK, so one is handed to it.
    return StubAnthropicLLM(client=anthropic_sdk.AsyncClient(api_key='test'), **kwargs)  # type: ignore[arg-type]


def test_openai_names_every_setting_but_top_k_and_thinking() -> None:
    model = StubOpenAILLM(model='gpt-4.1')
    plugin = plugin_for(model)
    assert plugin.name == 'openai'
    # OpenAI has no `top_k`, and `reasoning_effort` is unreachable on this plugin either way -- the
    # constructor sets it for every model that takes one, and the API refuses it on the rest.
    assert 'top_k' not in plugin.supported and 'thinking' not in plugin.supported
    settings = {key: value for key, value in ALL_SETTINGS.items() if key in plugin.supported}
    lowered, collisions = lower(settings, model, plugin)
    assert collisions == []
    assert lowered.extra_kwargs == {
        'max_completion_tokens': 512,
        'temperature': 0.3,
        'top_p': 0.9,
        'seed': 7,
        'presence_penalty': 0.1,
        'frequency_penalty': 0.2,
        'stop': ['END'],
    }
    assert lowered.parallel_tool_calls is False
    assert lowered.timeout == 4.5


def test_anthropic_takes_top_k_and_not_max_tokens() -> None:
    model = anthropic_llm(model='claude-sonnet-4-6')
    plugin = plugin_for(model)
    assert plugin.name == 'anthropic'
    # The plugin writes `max_tokens` on every request, defaulting to 1024, so a published value for it
    # would be overwritten rather than applied; `thinking` needs a token budget the contract has not got.
    assert 'max_tokens' not in plugin.supported and 'thinking' not in plugin.supported
    settings = {key: value for key, value in ALL_SETTINGS.items() if key in plugin.supported}
    lowered, collisions = lower(settings, model, plugin)
    assert collisions == []
    assert lowered.extra_kwargs == {'temperature': 0.3, 'top_p': 0.9, 'top_k': 40, 'stop_sequences': ['END']}


def test_google_has_no_parallel_tool_calls_effort_level_or_penalties() -> None:
    model = google.LLM(model='gemini-2.5-flash')
    plugin = plugin_for(model)
    assert plugin.name == 'google'
    assert 'parallel_tool_calls' not in plugin.supported and 'thinking' not in plugin.supported
    # The Gemini API answers `400 Penalty is not enabled for models/<model>` for either of these.
    assert 'presence_penalty' not in plugin.supported and 'frequency_penalty' not in plugin.supported
    lowered, collisions = lower({'max_tokens': 512, 'top_k': 40}, model, plugin)
    assert collisions == []
    assert lowered.extra_kwargs == {'max_output_tokens': 512, 'top_k': 40}
    assert lowered.parallel_tool_calls is NOT_GIVEN
    # And the baseline says nothing about a knob the plugin does not have, either.
    assert code_settings(model, plugin) == {}


def test_a_model_from_no_known_plugin_gets_only_what_chat_defines() -> None:
    plugin = plugin_for(StubLLM())
    assert plugin.name == ''
    assert plugin.supported == frozenset({'parallel_tool_calls', 'timeout'})


def test_livekit_inference_is_shaped_like_openai_and_keeps_the_effort_level() -> None:
    model = InferenceLLM('openai/gpt-4.1', extra_kwargs={'temperature': 0.9})
    plugin = plugin_for(model)
    assert plugin.name == 'openai'
    # Unlike the plugin, Inference never writes `reasoning_effort` itself, so it stays reachable.
    assert 'thinking' in plugin.supported
    assert lower({'thinking': 'high'}, model, plugin)[0].extra_kwargs == {'reasoning_effort': 'high'}
    lowered, collisions = lower({'temperature': 0.3, 'top_p': 0.5}, model, plugin)
    # Inference keeps its constructor patch in one dict, and writes it over the per-request one.
    assert lowered.extra_kwargs == {'top_p': 0.5}
    assert collisions == [
        "Managed agent config sets 'temperature' to 0.3, but the LiveKit openai plugin was constructed "
        "with 'temperature' and writes its own value over the per-request one; that setting is not "
        'applied. Leave it off the constructor to manage it from Logfire.'
    ]


def test_an_on_off_thinking_setting_has_nowhere_to_go() -> None:
    model = InferenceLLM('openai/gpt-5.1')
    _, collisions = lower({'thinking': True}, model, plugin_for(model))
    assert collisions == [
        "Managed agent config sets 'thinking' to True, which the LiveKit openai plugin has no on/off "
        'equivalent for -- it takes an effort level; that setting is not applied.'
    ]


def test_the_baseline_reads_settings_back_through_the_same_table() -> None:
    model = StubOpenAILLM(model='gpt-4.1', temperature=0.2, max_completion_tokens=256, parallel_tool_calls=True)
    assert code_settings(model, plugin_for(model)) == {
        'max_tokens': 256,
        'temperature': 0.2,
        'parallel_tool_calls': True,
    }


def test_an_effort_the_contract_has_no_level_for_is_named_and_left_to_the_core() -> None:
    """`'none'` is an effort level `AgentConfigSettings` cannot hold, and is not this table's to drop.

    The contract's rule for a value it cannot describe is to omit *and report* it, and the core is
    where both happen -- so this reads the model's value back rather than deciding on its own.
    """
    none_effort = InferenceLLM('openai/gpt-5.1', extra_kwargs={'reasoning_effort': 'none'})
    assert code_settings(none_effort, plugin_for(none_effort))['thinking'] == 'none'
    known = InferenceLLM('openai/gpt-5.1', extra_kwargs={'reasoning_effort': 'low'})
    assert code_settings(known, plugin_for(known))['thinking'] == 'low'
    # And a model that names no effort level says nothing about one.
    silent = InferenceLLM('openai/gpt-4.1')
    assert 'thinking' not in code_settings(silent, plugin_for(silent))


def test_anthropic_baseline_reports_top_k() -> None:
    model = anthropic_llm(model='claude-sonnet-4-6', temperature=0.5, top_k=40)
    assert code_settings(model, plugin_for(model)) == {'temperature': 0.5, 'top_k': 40}


def test_code_settings_carry_to_a_plugin_that_has_a_name_for_them() -> None:
    code = anthropic_llm(model='claude-sonnet-4-6', temperature=0.5, top_k=40)
    carried, lost = carry_settings(code, plugin_for(StubOpenAILLM(model='gpt-5.2')))
    assert carried == {'temperature': 0.5}
    assert lost == [
        'This agent is built with top_k=40, which the LiveKit openai plugin the managed agent config '
        'moves it to has no equivalent for; the published model runs without it.'
    ]


async def test_settings_reach_the_request(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__checkout',
        {'settings': {'temperature': 0.1, 'max_tokens': 64, 'parallel_tool_calls': False, 'timeout': 2.5}},
    )
    stub = StubOpenAILLM(model='gpt-4.1')
    await run(managed()(), stub)
    first = stub.requests[0]
    assert first.extra_kwargs == {'temperature': 0.1, 'max_completion_tokens': 64}
    assert first.parallel_tool_calls is False
    assert first.conn_options.timeout == 2.5


async def test_a_setting_the_plugin_has_no_knob_for_is_reported(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'settings': {'top_k': 40}})
    with pytest.warns(UserWarning, match="sets 'top_k', which this agent framework has no equivalent for"):
        await run(managed()(), StubOpenAILLM(model='gpt-4.1'))


async def test_a_constructor_value_wins_and_says_so(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout', {'settings': {'temperature': 0.1}})
    stub = StubOpenAILLM(model='gpt-4.1', temperature=0.9)
    with pytest.warns(UserWarning, match='writes its own value over the per-request one'):
        await run(managed()(), stub)
    assert stub.requests[0].extra_kwargs is NOT_GIVEN


async def test_a_model_only_publish_keeps_the_code_settings(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changing the model must not silently reset the temperature and token budget chosen in code."""
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.2'})
    swapped = StubOpenAILLM(model='gpt-5.2')
    monkeypatch.setattr('logfire.agent_control.livekit._agent.build', build_stub(swapped))

    code_model = StubOpenAILLM(model='gpt-4.1', temperature=0.2, max_completion_tokens=256)
    await run(managed()(), code_model)
    assert swapped.requests[0].extra_kwargs == {'temperature': 0.2, 'max_completion_tokens': 256}


async def test_a_published_setting_still_beats_the_code_one_it_carried(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.2', 'settings': {'temperature': 0.9}})
    swapped = StubOpenAILLM(model='gpt-5.2')
    monkeypatch.setattr('logfire.agent_control.livekit._agent.build', build_stub(swapped))

    code_model = StubOpenAILLM(model='gpt-4.1', temperature=0.2, max_completion_tokens=256)
    await run(managed()(), code_model)
    assert swapped.requests[0].extra_kwargs == {'temperature': 0.9, 'max_completion_tokens': 256}


async def test_a_code_setting_the_new_plugin_cannot_take_is_reported(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(project, 'agent__checkout', {'model': 'openai:gpt-5.2'})
    swapped = StubOpenAILLM(model='gpt-5.2')
    monkeypatch.setattr('logfire.agent_control.livekit._agent.build', build_stub(swapped))

    code_model = anthropic_llm(model='claude-sonnet-4-6', top_k=40)
    with pytest.warns(UserWarning, match='This agent is built with top_k=40'):
        await run(managed()(), code_model)
    assert swapped.requests[0].extra_kwargs is NOT_GIVEN
