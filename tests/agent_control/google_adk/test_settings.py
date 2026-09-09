"""Model settings, in the contract's names on one side and ADK's `GenerateContentConfig` on the other."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any

import pytest
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.gemma_llm import Gemma
from google.adk.models.google_llm import Gemini
from google.genai import types
from inline_snapshot import snapshot

from logfire.agent_control.google_adk import _settings, agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import FakeLlm, fake_llm, publish, run

pytestmark = pytest.mark.anyio


def managed(project: LocalVariableProvider, settings: dict[str, Any], **agent_kwargs: Any) -> tuple[LlmAgent, FakeLlm]:
    """An agent with a published settings patch, and the model that records what it was asked."""
    publish(project, {'settings': settings})
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, **agent_kwargs), label='production')
    return agent, llm


def applied(llm: FakeLlm) -> dict[str, Any]:
    """The settings one recorded request carried, without what ADK puts there itself."""
    config = llm.requests[0].config
    return config.model_dump(exclude_none=True, exclude={'labels', 'tools'}, mode='json')


async def test_every_setting_adk_has_a_knob_for(project: LocalVariableProvider) -> None:
    agent, llm = managed(
        project,
        {
            'max_tokens': 2048,
            'temperature': 0.4,
            'top_p': 0.8,
            'top_k': 40,
            'seed': 7,
            'presence_penalty': 0.1,
            'frequency_penalty': 0.2,
            'stop_sequences': ['END'],
        },
        # The published patch wins over the agent's own value, and leaves what it does not name.
        generate_content_config=types.GenerateContentConfig(temperature=0.9, candidate_count=1),
    )
    await run(agent)
    assert applied(llm) == snapshot(
        {
            'system_instruction': 'You are an agent. Your internal name is "checkout".',
            'temperature': 0.4,
            'top_p': 0.8,
            'top_k': 40.0,
            'candidate_count': 1,
            'max_output_tokens': 2048,
            'stop_sequences': ['END'],
            'presence_penalty': 0.1,
            'frequency_penalty': 0.2,
            'seed': 7,
        }
    )


async def test_a_timeout_is_published_in_seconds_and_sent_in_milliseconds(
    project: LocalVariableProvider,
) -> None:
    """And the rest of `http_options`, which is where headers and a client live, is left alone."""
    agent, llm = managed(
        project,
        {'timeout': 2.5},
        generate_content_config=types.GenerateContentConfig(
            http_options=types.HttpOptions(headers={'x-team': 'checkout'})
        ),
    )
    await run(agent)
    assert applied(llm) == snapshot(
        {
            'http_options': {'headers': {'x-team': 'checkout'}, 'timeout': 2500},
            'system_instruction': 'You are an agent. Your internal name is "checkout".',
        }
    )


async def test_a_timeout_on_an_agent_that_set_no_http_options(project: LocalVariableProvider) -> None:
    agent, llm = managed(project, {'timeout': 2.5})
    await run(agent)
    assert applied(llm)['http_options'] == snapshot({'timeout': 2500})


@pytest.mark.parametrize(
    ('thinking', 'expected'),
    [
        ('low', {'thinking_level': 'LOW'}),
        ('high', {'thinking_level': 'HIGH'}),
        (True, {'thinking_budget': -1}),
        # A backend that takes levels is asked for the minimal one rather than for a zero budget,
        # which is what Gemini 3 replaced the zero budget with; see `test_live_gemini.py`.
        (False, {'thinking_level': 'MINIMAL'}),
    ],
)
async def test_thinking_becomes_a_level_or_a_budget(
    project: LocalVariableProvider, thinking: Any, expected: dict[str, Any]
) -> None:
    agent, llm = managed(project, {'thinking': thinking})
    await run(agent)
    assert applied(llm)['thinking_config'] == expected


@pytest.mark.parametrize(
    ('model', 'thinking', 'expected'),
    [
        # Gemini 2.5 has no `thinking_level` at all and counts thinking in tokens.
        ('gemini-2.5-flash-lite', False, {'thinking_budget': 0}),
        ('gemini-2.5-flash-lite', True, {'thinking_budget': -1}),
        # Gemini 3 refuses a zero budget and takes a level instead; an automatic budget still works.
        ('gemini-3.5-flash-lite', False, {'thinking_level': 'MINIMAL'}),
        ('gemini-3.5-flash-lite', True, {'thinking_budget': -1}),
        ('gemini-3.5-flash-lite', 'low', {'thinking_level': 'LOW'}),
        # An alias names no generation, and today's aliases are Gemini 3 models.
        ('gemini-flash-lite-latest', False, {'thinking_level': 'MINIMAL'}),
    ],
)
def test_which_thinking_a_gemini_model_is_asked_for_follows_its_generation(
    model: str, thinking: Any, expected: dict[str, Any]
) -> None:
    """Both spellings 400 on the generation that does not take them; see `test_live_gemini.py`."""
    config = types.GenerateContentConfig()
    assert _settings.apply(config, {'thinking': thinking}, _settings.backend_of(Gemini(model=model))) == []
    assert config.model_dump(exclude_none=True, mode='json')['thinking_config'] == expected


async def test_a_thinking_level_a_gemini_2_model_has_no_field_for_is_reported(
    project: LocalVariableProvider,
) -> None:
    """`400 Thinking level is not supported for this model` is not a value going unapplied quietly."""
    config = types.GenerateContentConfig()
    backend = _settings.backend_of(Gemini(model='gemini-2.5-flash-lite'))
    assert _settings.apply(config, {'thinking': 'low'}, backend) == [
        snapshot(
            "Managed agent config sets thinking to 'low', which the Gemini model serving this request has no "
            'thinking level for; that setting is not applied.'
        )
    ]
    assert config.thinking_config is None


def test_a_penalty_no_gemini_model_accepts_is_left_off_the_request() -> None:
    """`400 Penalty is not enabled for models/<name>` on every Gemini model tried; see `test_live_gemini.py`.

    ADK forwards them -- it is the provider that refuses -- so this is the one row in the table that
    is about what the API takes rather than about what ADK reads.
    """
    config = types.GenerateContentConfig()
    backend = _settings.backend_of(Gemini(model='gemini-2.5-flash-lite'))
    assert _settings.apply(
        config, {'presence_penalty': 0.1, 'frequency_penalty': 0.2, 'temperature': 0.3}, backend
    ) == [
        snapshot(
            "Managed agent config sets 'presence_penalty', which the Gemini model serving this request does not "
            'read; that setting is not applied.'
        ),
        snapshot(
            "Managed agent config sets 'frequency_penalty', which the Gemini model serving this request does not "
            'read; that setting is not applied.'
        ),
    ]
    assert config.model_dump(exclude_none=True, mode='json') == snapshot({'temperature': 0.3})


async def test_a_thinking_level_adk_does_not_have_is_reported(project: LocalVariableProvider) -> None:
    """Rounding `xhigh` down to `high` would run an agent nobody asked for and say nothing."""
    agent, llm = managed(project, {'thinking': 'xhigh'})
    with pytest.warns(UserWarning, match="sets thinking to 'xhigh', which the model serving this request has no"):
        await run(agent)
    assert 'thinking_config' not in applied(llm)


async def test_a_setting_adk_cannot_express_at_all_is_reported(project: LocalVariableProvider) -> None:
    """`parallel_tool_calls` is a constructor argument on a LiteLLM model, not a per-request field."""
    agent, _ = managed(project, {'parallel_tool_calls': False})
    with pytest.warns(UserWarning, match="sets 'parallel_tool_calls', which this agent framework has no"):
        await run(agent)


async def test_a_published_thinking_level_replaces_the_planners(project: LocalVariableProvider) -> None:
    """A published effort next to the planner's own budget would be neither of the two values."""
    from google.adk.planners.built_in_planner import BuiltInPlanner

    agent, llm = managed(
        project,
        {'thinking': 'medium'},
        planner=BuiltInPlanner(thinking_config=types.ThinkingConfig(thinking_budget=128)),
    )
    await run(agent)
    assert applied(llm)['thinking_config'] == snapshot({'thinking_level': 'MEDIUM'})


@pytest.mark.parametrize(
    ('config', 'described'),
    [
        (None, {}),
        (types.GenerateContentConfig(temperature=0.1, max_output_tokens=512), {'temperature': 0.1, 'max_tokens': 512}),
        (types.GenerateContentConfig(top_k=40.0), {'top_k': 40}),
        # A `top_k` the contract has no integer for describes nothing it could say.
        (types.GenerateContentConfig(top_k=40.5), {}),
        (types.GenerateContentConfig(http_options=types.HttpOptions(timeout=5000)), {'timeout': 5.0}),
        (
            types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MEDIUM)
            ),
            {'thinking': 'medium'},
        ),
        (types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=-1)), {'thinking': True}),
        (types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=0)), {'thinking': False}),
        # Only a thought signature, which says nothing about how much the model thinks.
        (types.GenerateContentConfig(thinking_config=types.ThinkingConfig(include_thoughts=True)), {}),
        # Provider-specific settings stay in code: the baseline is readable by the whole project.
        (types.GenerateContentConfig(safety_settings=[], cached_content='projects/x/cachedContents/y'), {}),
    ],
)
def test_the_baseline_describes_the_settings_the_contract_has_names_for(
    config: types.GenerateContentConfig | None, described: dict[str, Any]
) -> None:
    assert _settings.describe(config, _settings.UNKNOWN_BACKEND) == described


def test_the_backend_serving_a_request_is_found_through_the_class_it_inherits_from() -> None:
    """`Gemma` is a `Gemini`, and reads the request config the way one does."""
    assert _settings.backend_of(Gemini(model='gemini-2.5-flash')) is _settings._GEMINI
    # A name with no Gemini generation in it is served as a current model, aliases and `Gemma` alike.
    assert _settings.backend_of(Gemma(model='gemma-3-27b-it')) is _settings._GEMINI_WITH_THINKING_LEVELS
    # A model class this adapter has never heard of is assumed to read the whole request config.
    assert _settings.backend_of(fake_llm()) is _settings.UNKNOWN_BACKEND


def test_every_backend_this_adapter_knows_is_still_where_it_says_it_is() -> None:
    """The table is keyed by name because `anthropic` and `litellm` are extras, so it needs a guard.

    Importing those classes would need provider extras this package deliberately does not depend on,
    and reading ADK's own source is what catches the day one of them is moved or renamed -- which
    would otherwise silently downgrade every Claude or LiteLLM agent to the unknown backend.
    """
    for path in _settings._BACKENDS:
        module_name, _, class_name = path.rpartition('.')
        spec = importlib.util.find_spec(module_name)
        assert spec is not None and spec.origin is not None
        module = ast.parse(Path(spec.origin).read_text())
        assert any(isinstance(node, ast.ClassDef) and node.name == class_name for node in module.body), (
            f'{path} is not a class Google ADK defines any more'
        )


@pytest.mark.parametrize(
    ('backend', 'settings', 'expected', 'unapplied'),
    [
        # Claude reads none of these three out of a `GenerateContentConfig`, so setting them would
        # show a value in Logfire that the request never carries.
        (
            _settings._CLAUDE,
            {'seed': 7, 'presence_penalty': 0.1, 'timeout': 2.5, 'max_tokens': 512},
            {'max_output_tokens': 512},
            [
                "sets 'seed', which the Claude model serving this request does not read",
                "sets 'presence_penalty', which the Claude model serving this request does not read",
                "sets 'timeout', which the Claude model serving this request does not read",
            ],
        ),
        # ADK refuses to send `thinking_level` to Anthropic, but a budget it does send.
        (_settings._CLAUDE, {'thinking': True}, {'thinking_config': {'thinking_budget': -1}}, []),
        (
            _settings._CLAUDE,
            {'thinking': 'high'},
            {},
            ["sets thinking to 'high', which the Claude model serving this request has no thinking level for"],
        ),
        # LiteLLM maps the penalties and the timeout, and reads no thinking config at all.
        (
            _settings._LITELLM,
            {'presence_penalty': 0.1, 'timeout': 2.5, 'seed': 7, 'thinking': True},
            {'presence_penalty': 0.1, 'http_options': {'timeout': 2500}},
            [
                "sets 'seed', which the LiteLLM model serving this request does not read",
                'sets thinking to True, which the LiteLLM model serving this request has no thinking level for',
            ],
        ),
    ],
)
def test_only_what_the_backend_reads_reaches_the_request(
    backend: _settings.Backend, settings: dict[str, Any], expected: dict[str, Any], unapplied: list[str]
) -> None:
    config = types.GenerateContentConfig()
    messages = _settings.apply(config, settings, backend)
    assert config.model_dump(exclude_none=True, mode='json') == expected
    assert len(messages) == len(unapplied)
    for message, fragment in zip(messages, unapplied):
        assert fragment in message


async def test_a_setting_the_published_model_does_not_read_is_reported(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The backend that decides is the one *serving* the request, published switch included."""
    monkeypatch.setitem(_settings._BACKENDS, f'{FakeLlm.__module__}.{FakeLlm.__qualname__}', _settings._CLAUDE)
    agent, llm = managed(project, {'seed': 7, 'temperature': 0.4})
    with pytest.warns(UserWarning, match="sets 'seed', which the Claude model serving this request does not read"):
        await run(agent)
    assert 'seed' not in applied(llm)
    assert applied(llm)['temperature'] == snapshot(0.4)


def test_the_baseline_leaves_out_what_the_agents_own_model_ignores() -> None:
    """A value the agent sets and its backend drops is not part of what the agent does."""
    config = types.GenerateContentConfig(
        temperature=0.1,
        seed=7,
        http_options=types.HttpOptions(timeout=5000),
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
    )
    assert _settings.describe(config, _settings._CLAUDE) == snapshot({'temperature': 0.1})
    assert _settings.describe(config, _settings._LITELLM) == snapshot({'temperature': 0.1, 'timeout': 5.0})
    assert _settings.describe(config, _settings._GEMINI) == snapshot({'temperature': 0.1, 'seed': 7, 'timeout': 5.0})
    assert _settings.describe(config, _settings._GEMINI_WITH_THINKING_LEVELS) == snapshot(
        {'temperature': 0.1, 'seed': 7, 'timeout': 5.0, 'thinking': 'low'}
    )
