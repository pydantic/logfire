"""What a published config does to a request a real OpenAI model answers.

The rest of this suite drives the SDK's own runner against a stub model, which proves what the
adapter hands the model and nothing about what the provider does with it. These tests record the
wire: the request body OpenAI actually received, and the answer it actually gave. That is the only
way to settle the claims the adapter's docs make on the provider's behalf -- that a Responses request
carries no penalties, that the settings the table calls editable are accepted rather than refused --
because those were read off SDK source, not observed.

Recorded against `gpt-5.4-nano`, the cheapest model the account offers, and replayed from the
cassettes beside this file with no credentials.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from agents import Agent, ModelSettings, Runner, function_tool
from agents.items import ToolCallItem
from inline_snapshot import snapshot
from openai import BadRequestError
from openai.types.responses import ResponseFunctionToolCall
from vcr.cassette import Cassette

from logfire.agent_control.openai_agents import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import get_weather, publish

pytestmark = pytest.mark.anyio

MODEL = 'gpt-5.4-nano'
"""The cheapest model on the account, and a Responses model, which is what the claims below are about."""


def request_bodies(cassette: Cassette) -> list[dict[str, Any]]:
    """Every request body this cassette recorded, in order, as the JSON OpenAI was sent."""
    requests = cast('list[Any]', cassette.requests)  # pyright: ignore[reportUnknownMemberType]
    return [json.loads(request.body) for request in requests]


@pytest.mark.vcr()
async def test_a_published_instruction_block_reaches_the_model(project: LocalVariableProvider, vcr: Cassette) -> None:
    """A replaced block and an added one, in the `instructions` field of a real request."""
    publish(
        project,
        'agent__live_assistant',
        {
            'instructions': [
                {'id': 'agent', 'instructions': 'Reply with exactly the word BANANA.'},
                'Never add punctuation.',
            ]
        },
    )
    agent = agent_control(
        Agent(name='live_assistant', instructions='You are a helpful assistant.', model=MODEL),
        label='production',
    )

    result = await Runner.run(agent, 'What is the capital of France?')

    # The prompt the provider was sent is the published one, joined the way the adapter joins blocks.
    assert request_bodies(vcr)[0]['instructions'] == snapshot(
        'Reply with exactly the word BANANA.\n\nNever add punctuation.'
    )
    # And the model did what it said, which is the half a request body cannot show.
    assert str(result.final_output).strip() == snapshot('BANANA')


@pytest.mark.vcr()
async def test_a_renamed_tool_is_called_under_its_managed_name_and_routes_back(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """The whole rename round trip against a model that really chooses to call the tool.

    Four things have to hold at once, and only a real model can produce the middle two: the tool is
    advertised under the managed name with the managed descriptions, the model calls *that* name, the
    call reaches the function the code wrote with the arguments it declared, and everything the run
    hands back to user code still says `get_weather`.
    """
    looked_up: list[str] = []

    @function_tool
    def get_weather(city: str) -> str:
        """Get the current weather for a city.

        Args:
            city: City to look up.
        """
        looked_up.append(city)
        return f'sunny in {city}'

    publish(
        project,
        'agent__live_forecaster',
        {
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'new_name': 'lookup_weather',
                    'description': 'Look up the current weather in a city.',
                    'parameters': {'city': {'description': "The city to look up, for example 'Paris'."}},
                }
            ]
        },
    )
    agent = agent_control(
        Agent(
            name='live_forecaster',
            instructions='Use your tools to answer. Answer in one short sentence.',
            tools=[get_weather],
            model=MODEL,
        ),
        label='production',
    )

    result = await Runner.run(agent, 'What is the weather in Paris?')

    first, second = request_bodies(vcr)
    # The model is offered the managed name, the managed description, and the managed wording of the
    # parameter -- the three things the contract says are editable, on the wire.
    assert [(tool['name'], tool['description']) for tool in first['tools']] == snapshot(
        [('lookup_weather', 'Look up the current weather in a city.')]
    )
    assert first['tools'][0]['parameters']['properties']['city']['description'] == snapshot(
        "The city to look up, for example 'Paris'."
    )
    # It called that name, and the next turn is shown its own call under that name too.
    assert [item['name'] for item in second['input'] if item.get('type') == 'function_call'] == snapshot(
        ['lookup_weather']
    )
    # The function the code wrote ran, with the argument its own schema declares.
    assert looked_up == snapshot(['Paris'])
    # And nothing user code can see was renamed.
    calls = [item.raw_item for item in result.new_items if isinstance(item, ToolCallItem)]
    assert [call.name for call in calls if isinstance(call, ResponseFunctionToolCall)] == snapshot(['get_weather'])
    assert 'sunny' in str(result.final_output).lower()


@pytest.mark.vcr()
async def test_the_settings_the_table_calls_editable_are_accepted_by_the_provider(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """Every canonical setting the adapter says it can lower, sent to OpenAI in one request.

    The claim being checked is that the provider *takes* them: a setting the table offers and the API
    refuses would be a knob the Logfire editor shows and the agent cannot turn. `thinking: false` is
    the contract's boolean, and it goes out as the effort the SDK spells "do not reason".

    The agent is given a tool it has no reason to call, because `parallel_tool_calls` is the one
    setting here that a request with no tools in it leaves out entirely.
    """
    publish(
        project,
        'agent__live_tuned',
        {
            'settings': {
                'temperature': 0.4,
                'top_p': 0.9,
                'max_tokens': 2048,
                'parallel_tool_calls': True,
                'thinking': False,
            }
        },
    )
    agent = agent_control(
        Agent(name='live_tuned', instructions='Answer in one word.', tools=[get_weather], model=MODEL),
        label='production',
    )

    result = await Runner.run(agent, 'What is the capital of France?')

    body = request_bodies(vcr)[0]
    assert {key: body[key] for key in ('temperature', 'top_p', 'max_output_tokens', 'parallel_tool_calls')} == snapshot(
        {'temperature': 0.4, 'top_p': 0.9, 'max_output_tokens': 2048, 'parallel_tool_calls': True}
    )
    assert body['reasoning']['effort'] == snapshot('none')
    assert str(result.final_output).strip() == snapshot('Paris')


@pytest.mark.vcr()
async def test_a_reasoning_model_refuses_the_sampling_settings_once_thinking_is_on(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """Two settings the table calls editable, refused by the provider for the model they were sent to.

    `temperature` and `top_p` are `ModelSettings` fields, the Responses model does send them, and
    OpenAI's own reasoning models take them -- right up until the same request asks the model to
    reason, and then the API refuses the request outright rather than ignoring the pair. So the two
    are editable, and a config that publishes either *alongside* `thinking` on a GPT-5-class model
    fails every request the agent makes.

    That is a provider rule about one model, not something the adapter can see: nothing in
    `ModelSettings`, in the SDK, or in the contract says which efforts a given model will accept a
    sampling setting with, and dropping a published value on a guess would be the silent
    "shown as applied, never applied" the whole design is against. It is documented instead.
    """
    publish(project, 'agent__live_conflicted', {'settings': {'temperature': 0.4, 'thinking': 'low'}})
    agent = agent_control(
        Agent(name='live_conflicted', instructions='Answer in one word.', model=MODEL), label='production'
    )

    with pytest.raises(BadRequestError) as exc_info:
        await Runner.run(agent, 'What is the capital of France?')

    assert exc_info.value.message == snapshot(
        "Error code: 400 - {'error': {'message': \"Unsupported parameter: 'temperature' is not supported with this model.\", 'type': 'invalid_request_error', 'param': 'temperature', 'code': None}}"
    )
    body = request_bodies(vcr)[0]
    assert (body['temperature'], body['reasoning']['effort']) == snapshot((0.4, 'low'))


@pytest.mark.vcr()
async def test_a_responses_request_carries_neither_penalty(project: LocalVariableProvider, vcr: Cassette) -> None:
    """The one "Conditional" row in the table, checked against the request that was really sent.

    `ModelSettings` has both fields because the Chat Completions and LiteLLM models send them, and
    the adapter refuses to apply either on a Responses model on the grounds that the Responses model
    never puts them in a request. That was read off the SDK; this is the request.
    """
    publish(project, 'agent__live_penalised', {'settings': {'presence_penalty': 1.0, 'frequency_penalty': 1.0}})
    agent = agent_control(
        Agent(
            name='live_penalised',
            instructions='Answer in one word.',
            model=MODEL,
            model_settings=ModelSettings(presence_penalty=0.5, frequency_penalty=0.5),
        ),
        label='production',
        # The refusal itself is reported, and asserted on offline; what is under test here is the
        # request, so the report is silenced rather than turned into this test's subject.
        on_unmatched='ignore',
    )

    result = await Runner.run(agent, 'What is the capital of France?')

    body = request_bodies(vcr)[0]
    assert [key for key in ('presence_penalty', 'frequency_penalty') if key in body] == snapshot([])
    assert str(result.final_output).strip() == snapshot('Paris')


async def test_a_setting_only_extra_args_could_carry_never_reaches_the_provider() -> None:
    """`top_k`, `seed` and `stop_sequences`: the three rows the table marks "No", and why.

    No cassette, because there is nothing to record: the failure happens in the OpenAI client's own
    signature, before a request is built. That is the finding -- an `extra_args` key the Responses
    API has no parameter for is not sent and ignored, and is not refused by the API either; it raises
    locally, so forwarding one of these would turn a published setting into a `TypeError` on every
    request the agent makes.
    """
    for setting in ('top_k', 'seed', 'stop_sequences'):
        agent = Agent(name='live_unsettable', model=MODEL, model_settings=ModelSettings(extra_args={setting: 1}))
        with pytest.raises(TypeError, match=f'unexpected keyword argument {setting!r}'):
            await Runner.run(agent, 'hello')
