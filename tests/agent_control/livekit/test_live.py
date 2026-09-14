"""What a real provider does with what this adapter sends it.

Every test here drives one real `AgentSession` turn, through a real LiveKit plugin, against a real
provider, and then reads the request back off the VCR cassette. That is the point: the tests beside
this one drive the real framework against stub models, which proves the adapter's integration but
can only ever confirm what this package *believes* a plugin does with a setting. The claims in
`_settings.py` were written by reading plugin source, and the wire is the only place they can be
checked -- twice over, because the cassette carries both the request that went out and the status the
provider answered with.

Recorded with real credentials in the environment:

    uv run --env-file <file-with-the-keys> pytest tests/agent_control/livekit/test_live.py \
        --record-mode=rewrite

and replayed from `cassettes/test_live/` with none, which is how CI runs them.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic as anthropic_sdk
import pytest
from livekit.agents import llm
from livekit.agents.voice.run_result import RunResult
from livekit.plugins import anthropic, openai
from vcr.cassette import Cassette

from logfire.variables.local import LocalVariableProvider

from ..conftest import publish
from .agents import get_weather, managed, outputs, run

pytestmark = [pytest.mark.anyio, pytest.mark.vcr()]

# The cheapest current model of each provider, since a cassette does not care how good the answer is.
OPENAI_MODEL = 'gpt-4.1-nano'
ANTHROPIC_MODEL = 'claude-haiku-4-5'

# There is no Google test here, and not for want of a table to check: `vcrpy` cannot record what
# `google-genai` streams. It replaces the transport's response stream with a replayable one, and the
# SSE reader in `google.genai._api_client` then yields no chunks at all from a response the cassette
# shows arriving whole and `200`, so every LiveKit google request fails as "no response generated".
# Reproducible in four lines against `generate_content_stream` with no LiveKit in the picture. The
# Google row was checked against the live API directly instead, which is where the two penalties
# `_settings.py` no longer claims come from.


def model_requests(cassette: Cassette) -> list[tuple[Any, Any]]:
    """The recorded model requests, paired with their responses.

    Only the `POST`s: a plugin also probes its provider on the way up -- the OpenAI one asks
    `GET /v1/models` -- and those are not what this module is about.
    """
    return [pair for pair in zip(cassette.requests, cassette.responses) if pair[0].method == 'POST']


def sent(cassette: Cassette, index: int = 0) -> dict[str, Any]:
    """The JSON body of one recorded model request: what the provider was actually asked for."""
    return json.loads(model_requests(cassette)[index][0].body)


def status(cassette: Cassette, index: int = 0) -> int:
    """The status the provider answered that request with, which is whether it accepted it."""
    return model_requests(cassette)[index][1]['status']['code']


def said(result: RunResult) -> list[str]:
    """What the agent ended up saying, so a test can check the prompt changed the answer."""
    return [event.item.text_content or '' for event in result.events if event.type == 'message']


def anthropic_llm() -> llm.LLM:
    """The Anthropic plugin, given the client it can no longer build for itself.

    `livekit-plugins-anthropic` 1.8 hands its `anthropic.AsyncClient` an `httpx.AsyncClient`, and the
    `anthropic` SDK from 1.0 requires an `httpx2.AsyncClient` instead, so constructing the plugin the
    way its own README does raises `TypeError` in this resolution. Handing it a client built by the
    SDK itself is the only way to reach the plugin at all -- and it is also the shape a managed
    `model` swap produces, since that reuses the code model's client. See the docs page's known
    limits: the same SDK rewrite is why `temperature`, `top_p` and `top_k` are unreachable here.
    """
    return anthropic.LLM(model=ANTHROPIC_MODEL, client=anthropic_sdk.AsyncClient())


async def test_a_published_block_reaches_the_model(project: LocalVariableProvider, vcr: Cassette) -> None:
    """A published block is what the model is told, and it is what the model does."""
    publish(
        project,
        'agent__checkout',
        {'instructions': [{'id': 'agent', 'instructions': 'Whatever you are asked, reply with the single word FIG.'}]},
    )
    agent = managed(instructions='You are a helpful assistant. Answer questions about the weather.')()
    result = await run(agent, openai.LLM(model=OPENAI_MODEL), user_input='Weather in Paris?')

    assert sent(vcr)['messages'][0] == {
        'role': 'system',
        'content': 'Whatever you are asked, reply with the single word FIG.',
    }
    assert status(vcr) == 200
    assert 'FIG' in ' '.join(said(result))


async def test_a_renamed_tool_is_called_by_the_model_and_routed_home(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """The rename, the reworded description, and the reworded parameter, on one real request.

    A real model chooses the tool from what it is shown, so this is the only test that can say the
    managed name is the one it calls -- and `outputs` is the code side, under the code name.
    """
    publish(
        project,
        'agent__checkout',
        {
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'new_name': 'fetch_forecast',
                    'description': 'Fetch the forecast for a city. Always use this for weather questions.',
                    'parameters': {'city': {'description': 'The city to fetch the forecast for, e.g. London.'}},
                }
            ]
        },
    )
    agent = managed(instructions='You are a weather assistant. Use your tools.', tools=[get_weather])()
    result = await run(agent, openai.LLM(model=OPENAI_MODEL), user_input='What is the weather in Paris?')

    advertised = sent(vcr)['tools'][0]['function']
    assert advertised['name'] == 'fetch_forecast'
    assert advertised['description'] == 'Fetch the forecast for a city. Always use this for weather questions.'
    assert advertised['parameters']['properties']['city']['description'] == (
        'The city to fetch the forecast for, e.g. London.'
    )
    # The model called the name it was shown, and it is the name the second request replays.
    calls = [item for item in sent(vcr, 1)['messages'] if item.get('tool_calls')]
    assert [call['function']['name'] for item in calls for call in item['tool_calls']] == ['fetch_forecast']
    # The implementation ran under its own name, with the argument the model chose. Compared as a
    # set because how many times a real model calls a tool is its own business; where each call
    # lands is not.
    assert set(outputs(result)) == {('get_weather', 'weather(get_weather, Paris)')}


async def test_openai_accepts_every_setting_the_table_names(project: LocalVariableProvider, vcr: Cassette) -> None:
    """Every canonical setting the OpenAI table claims, on one request the API answered `200` to."""
    publish(
        project,
        'agent__checkout',
        {
            'settings': {
                'max_tokens': 128,
                'temperature': 0.3,
                'top_p': 0.9,
                'seed': 7,
                'presence_penalty': 0.1,
                'frequency_penalty': 0.2,
                'stop_sequences': ['NEVERMIND'],
                'parallel_tool_calls': False,
                'timeout': 30,
            }
        },
    )
    # A tool, because OpenAI refuses `parallel_tool_calls` on a request that advertises none.
    agent = managed(instructions='You are a weather assistant.', tools=[get_weather])()
    await run(agent, openai.LLM(model=OPENAI_MODEL), user_input='Say hello.')

    body = sent(vcr)
    assert {key: body[key] for key in sorted(body) if key not in ('messages', 'model', 'tools', 'stream')} == {
        'frequency_penalty': 0.2,
        'max_completion_tokens': 128,
        'parallel_tool_calls': False,
        'presence_penalty': 0.1,
        'seed': 7,
        'stop': ['NEVERMIND'],
        'stream_options': {'include_usage': True},
        'temperature': 0.3,
        'top_p': 0.9,
    }
    assert status(vcr) == 200


async def test_anthropic_takes_a_published_prompt_a_rename_and_its_one_reachable_setting(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """The Anthropic plugin, driven end to end: prompt, rename, and `stop_sequences`.

    Only `stop_sequences`, because `anthropic` 1.x moved `temperature`, `top_p` and `top_k` off
    `messages.create()` and the plugin still passes them as keyword arguments; see `anthropic_llm`.
    """
    publish(
        project,
        'agent__checkout',
        {
            'instructions': [{'id': 'agent', 'instructions': 'You are a weather assistant. Use your tools.'}],
            'tool_definitions': [{'name': 'get_weather', 'new_name': 'fetch_forecast'}],
            'settings': {'stop_sequences': ['NEVERMIND']},
        },
    )
    agent = managed(instructions='CODE PROMPT', tools=[get_weather])()
    result = await run(agent, anthropic_llm(), user_input='What is the weather in Paris?')

    body = sent(vcr)
    assert body['system'][0]['text'] == 'You are a weather assistant. Use your tools.'
    assert body['tools'][0]['name'] == 'fetch_forecast'
    assert body['stop_sequences'] == ['NEVERMIND']
    assert status(vcr) == 200
    assert set(outputs(result)) == {('get_weather', 'weather(get_weather, Paris)')}


async def test_a_constructor_value_really_does_beat_the_published_one(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """The collision the README warns about, on the wire: the constructor's value is what goes out."""
    publish(project, 'agent__checkout', {'settings': {'temperature': 0.1, 'top_p': 0.5}})
    agent = managed(instructions='You are a helpful assistant.')()
    with pytest.warns(UserWarning, match='writes its own value over the per-request one'):
        await run(agent, openai.LLM(model=OPENAI_MODEL, temperature=0.9), user_input='Say hello.')

    body = sent(vcr)
    assert (body['temperature'], body['top_p']) == (0.9, 0.5)
    assert status(vcr) == 200
