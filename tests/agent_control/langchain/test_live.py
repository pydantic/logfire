"""The claims this adapter makes about a provider, checked against that provider.

Every other module here drives the real LangChain agent loop against a model that records what it
was handed, which settles what the middleware *sends*. This one settles the rest: the requests are
real, recorded once against OpenAI and Anthropic and replayed from `cassettes/` with no credentials,
and each assertion is either what a real model did with a published config or what a real API did
with a setting this adapter claims that integration accepts.

Re-record with:

    uv run --env-file <a file with OPENAI_API_KEY and ANTHROPIC_API_KEY> \
        pytest tests/agent_control/langchain/test_live.py --record-mode=rewrite

The models are the cheapest current one of each provider, because what is under test is the wire and
not the reasoning. Two of them are named a second time on purpose: a setting an integration accepts
is still a setting a *model generation* may refuse, and the pairs below are what says so.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from inline_snapshot import snapshot
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from vcr.cassette import Cassette

from logfire.agent_control.langchain import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import build_agent, declared_prompt, get_weather, publish, run

OPENAI_MODEL = 'gpt-5.4-nano'
"""OpenAI's cheapest current model. A reasoning model, which two of the tests below turn on."""

OPENAI_SAMPLING_MODEL = 'gpt-4.1-nano'
"""A current OpenAI model that is not a reasoning one, for the settings `OPENAI_MODEL` refuses."""

ANTHROPIC_MODEL = 'claude-haiku-4-5-20251001'
"""Anthropic's cheapest current model."""

ANTHROPIC_THINKING_MODEL = 'claude-fable-5-1'
"""A current Anthropic model whose generation has the effort control `ANTHROPIC_MODEL` lacks."""

PUBLISHED_BLOCK = 'The office mascot is a banana. When asked what the mascot is, answer with exactly: BANANA'
"""A published block whose text is the only place the answer to the question could have come from."""


def openai(model: str = OPENAI_MODEL) -> ChatOpenAI:
    return ChatOpenAI(model=model, max_completion_tokens=2048)


def anthropic(model: str = ANTHROPIC_MODEL) -> ChatAnthropic:
    # `max_tokens` is the field's own name; `max_tokens_to_sample` is the alias pyright builds
    # the constructor signature from, not seeing the `populate_by_name` the base class sets.
    return ChatAnthropic(model_name=model, max_tokens=2048, timeout=None, stop=None)  # pyright: ignore[reportCallIssue]


def sent(cassette: Cassette, index: int = 0) -> dict[str, Any]:
    """The JSON body of the `index`th request the provider actually received."""
    requests = cast('list[Any]', cassette.requests)  # pyright: ignore[reportUnknownMemberType]
    return cast('dict[str, Any]', json.loads(requests[index].body))


def weather_agent(model: BaseChatModel, **kwargs: Any) -> Any:
    """An agent with one tool and a prompt that gets a small model to reach for it."""
    return build_agent(
        model,
        agent_control(label='production', **kwargs),
        tools=[get_weather],
        system_prompt=declared_prompt('You are a weather assistant. Always use your tools to answer.'),
    )


@pytest.mark.vcr()
def test_a_published_block_is_what_openai_is_told(project: LocalVariableProvider, vcr: Cassette) -> None:
    publish(project, {'instructions': [{'id': 'system:role', 'instructions': PUBLISHED_BLOCK}]})
    agent = build_agent(
        openai(),
        agent_control(label='production', instructions={'role': 'You are a helpful assistant.'}),
        tools=[],
        system_prompt=None,
    )

    result = run(agent, 'What is the office mascot?')

    assert sent(vcr)['messages'] == snapshot(
        [
            {'role': 'system', 'content': PUBLISHED_BLOCK},
            {'role': 'user', 'content': 'What is the office mascot?'},
        ]
    )
    assert 'BANANA' in result['messages'][-1].text


@pytest.mark.vcr()
def test_a_published_block_is_what_anthropic_is_told(project: LocalVariableProvider, vcr: Cassette) -> None:
    publish(project, {'instructions': [{'id': 'system:role', 'instructions': PUBLISHED_BLOCK}]})
    agent = build_agent(
        anthropic(),
        agent_control(label='production', instructions={'role': 'You are a helpful assistant.'}),
        tools=[],
        system_prompt=None,
    )

    result = run(agent, 'What is the office mascot?')

    # Anthropic takes the system prompt in its own field rather than as a message, which is the
    # whole reason the adapter hands LangChain a `SystemMessage` and lets the integration lower it.
    assert sent(vcr)['system'] == snapshot(PUBLISHED_BLOCK)
    assert 'BANANA' in result['messages'][-1].text


@pytest.mark.vcr()
def test_openai_calls_the_managed_name_and_the_code_gets_its_own(project: LocalVariableProvider, vcr: Cassette) -> None:
    publish(
        project,
        {
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'new_name': 'lookup_weather',
                    'description': 'Look up the current weather in a city.',
                    'parameters': {'city': {'description': "The city to look up, such as 'Paris'."}},
                }
            ]
        },
    )

    result = run(weather_agent(openai()), "What's the weather in Paris?")

    # What the model was shown: the managed name, description and parameter description.
    assert sent(vcr)['tools'] == snapshot(
        [
            {
                'type': 'function',
                'function': {
                    'name': 'lookup_weather',
                    'description': 'Look up the current weather in a city.',
                    'parameters': {
                        'properties': {
                            'city': {'description': "The city to look up, such as 'Paris'.", 'type': 'string'}
                        },
                        'required': ['city'],
                        'type': 'object',
                    },
                },
            }
        ]
    )
    # What the model called it, on the wire, in its reply.
    assert sent(vcr, 1)['messages'][2]['tool_calls'][0]['function'] == snapshot(
        {'name': 'lookup_weather', 'arguments': '{"city": "Paris"}'}
    )
    # And what everything on this side of that boundary sees: the name the code gave the tool, the
    # arguments the code declared, and the reply the code's implementation produced.
    call, tool_message = result['messages'][1].tool_calls[0], result['messages'][2]
    assert (call['name'], call['args']) == ('get_weather', {'city': 'Paris'})
    assert (tool_message.name, tool_message.text) == ('get_weather', 'sunny in Paris')


@pytest.mark.vcr()
def test_anthropic_calls_the_managed_name_and_the_code_gets_its_own(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    publish(
        project,
        {
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'new_name': 'lookup_weather',
                    'description': 'Look up the current weather in a city.',
                    'parameters': {'city': {'description': "The city to look up, such as 'Paris'."}},
                }
            ]
        },
    )

    result = run(weather_agent(anthropic()), "What's the weather in Paris?")

    assert sent(vcr)['tools'] == snapshot(
        [
            {
                'name': 'lookup_weather',
                'description': 'Look up the current weather in a city.',
                'input_schema': {
                    'properties': {'city': {'description': "The city to look up, such as 'Paris'.", 'type': 'string'}},
                    'required': ['city'],
                    'type': 'object',
                },
            }
        ]
    )
    # Anthropic replays the assistant turn as content blocks rather than as an OpenAI-shaped
    # `tool_calls` list, so this is the other half of the rename: the history going back out says
    # the managed name too, or the provider would reject a `tool_use` naming a tool it never saw.
    replayed = [entry for entry in sent(vcr, 1)['messages'][1]['content'] if entry['type'] == 'tool_use']
    assert [(entry['name'], entry['input']) for entry in replayed] == snapshot([('lookup_weather', {'city': 'Paris'})])
    call, tool_message = result['messages'][1].tool_calls[0], result['messages'][2]
    assert (call['name'], call['args']) == ('get_weather', {'city': 'Paris'})
    assert (tool_message.name, tool_message.text) == ('get_weather', 'sunny in Paris')


OPENAI_SETTINGS: dict[str, Any] = {
    'max_tokens': 256,
    'temperature': 0.4,
    'top_p': 0.9,
    'seed': 7,
    'presence_penalty': 0.1,
    'frequency_penalty': 0.2,
    'parallel_tool_calls': False,
    'timeout': 30.0,
}
"""Every canonical setting `ChatOpenAI` declares a field for, minus the two that model refuses."""

ANTHROPIC_SETTINGS: dict[str, Any] = {
    'max_tokens': 256,
    'temperature': 0.4,
    'top_k': 5,
    'parallel_tool_calls': False,
    'timeout': 30.0,
    'stop_sequences': ['NEVERMIND'],
}
"""Every canonical setting `ChatAnthropic` declares a field for, minus `top_p` and `thinking`.

`top_p` is left out because Anthropic refuses a request carrying both it and `temperature`, which
`test_anthropic_refuses_temperature_and_top_p_together` records below; `thinking` because this model
generation has no effort control.
"""


@pytest.mark.vcr()
def test_openai_accepts_every_setting_this_adapter_sends_it(project: LocalVariableProvider, vcr: Cassette) -> None:
    publish(project, {'settings': OPENAI_SETTINGS})

    result = run(weather_agent(openai()), 'Say OK.')

    # A 200 in the cassette is the assertion: every one of these reached the API together and none
    # of them was refused. What went out is the contract's keys in the provider's own spelling --
    # all but `timeout`, which every integration keeps client-side as the HTTP deadline.
    body = sent(vcr)
    assert {name: body[name] for name in OPENAI_SETTINGS if name in body} | {
        'max_completion_tokens': body['max_completion_tokens']
    } == snapshot(
        {
            'temperature': 0.4,
            'top_p': 0.9,
            'seed': 7,
            'presence_penalty': 0.1,
            'frequency_penalty': 0.2,
            'parallel_tool_calls': False,
            'max_completion_tokens': 256,
        }
    )
    assert result['messages'][-1].text


@pytest.mark.vcr()
def test_anthropic_accepts_every_setting_this_adapter_sends_it(project: LocalVariableProvider, vcr: Cassette) -> None:
    publish(project, {'settings': ANTHROPIC_SETTINGS})

    result = run(weather_agent(anthropic()), 'Say OK.')

    body = sent(vcr)
    assert {name: value for name, value in body.items() if name not in ('messages', 'system', 'tools')} == snapshot(
        {
            'max_tokens': 256,
            'model': 'claude-haiku-4-5-20251001',
            'stop_sequences': ['NEVERMIND'],
            'tool_choice': {'type': 'auto', 'disable_parallel_tool_use': True},
            'temperature': 0.4,
            'top_k': 5,
        }
    )
    assert result['messages'][-1].text


@pytest.mark.vcr()
def test_stop_sequences_reach_a_model_that_takes_them(project: LocalVariableProvider, vcr: Cassette) -> None:
    # The mapping itself is right -- the contract's `stop_sequences` goes out as OpenAI's `stop` --
    # and the model that refused it above is what makes that worth saying separately.
    publish(project, {'settings': {'stop_sequences': ['NEVERMIND'], 'max_tokens': 64}})

    run(weather_agent(openai(OPENAI_SAMPLING_MODEL)), 'Say OK.')

    assert sent(vcr)['stop'] == snapshot(['NEVERMIND'])


@pytest.mark.vcr()
def test_thinking_reaches_a_model_that_takes_it(project: LocalVariableProvider, vcr: Cassette) -> None:
    publish(project, {'settings': {'thinking': 'low'}})

    run(weather_agent(anthropic(ANTHROPIC_THINKING_MODEL)), 'Say OK.')

    # `ChatAnthropic` lowers the contract's effort level to this model generation's own control.
    assert sent(vcr)['output_config'] == snapshot({'effort': 'low'})


@pytest.mark.vcr()
def test_openai_refuses_stop_sequences_on_a_reasoning_model(project: LocalVariableProvider) -> None:
    # The adapter applies a setting the *integration* declares a field for, which is as far as
    # anything here can see: whether this model generation takes it is the provider's answer, and it
    # is a request failure rather than something the adapter can report in advance.
    publish(project, {'settings': {'stop_sequences': ['NEVERMIND']}})

    with pytest.raises(Exception, match="Unsupported parameter: 'stop' is not supported with this model"):
        run(weather_agent(openai()), 'Say OK.')


@pytest.mark.vcr()
def test_openai_refuses_thinking_alongside_tools(project: LocalVariableProvider) -> None:
    publish(project, {'settings': {'thinking': 'low'}})

    with pytest.raises(Exception, match='Function tools with reasoning_effort are not supported'):
        run(weather_agent(openai()), 'Say OK.')


@pytest.mark.vcr()
def test_anthropic_refuses_thinking_on_a_model_generation_without_it(project: LocalVariableProvider) -> None:
    publish(project, {'settings': {'thinking': 'low'}})

    with pytest.raises(Exception, match='does not support the effort parameter'):
        run(weather_agent(anthropic()), 'Say OK.')


@pytest.mark.vcr()
def test_anthropic_refuses_temperature_and_top_p_together(project: LocalVariableProvider) -> None:
    publish(project, {'settings': {'temperature': 0.4, 'top_p': 0.9}})

    with pytest.raises(Exception, match='`temperature` and `top_p` cannot both be specified'):
        run(weather_agent(anthropic()), 'Say OK.')
