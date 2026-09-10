"""What a real Gemini model does with a published config, recorded once and replayed offline.

Every other test in this directory drives a real ADK `Runner` against a stub model, which proves
that a published value reaches the request ADK assembles. That leaves the other half of each claim
open: whether the *provider* does anything with what the request carries, and whether it accepts it
at all. These tests close that half against `gemini-2.5-flash-lite` -- the cheapest current Gemini
model -- and against `gemini-3.5-flash-lite` where a claim is about the difference between the two
generations.

They are recorded with `pytest-recording`, so they replay from `cassettes/test_live_gemini/` with no
credentials. Re-record with a real key in the environment:

```bash
uv run pytest tests/agent_control/google_adk/test_live_gemini.py --record-mode=rewrite
```

Assertions are made on the recorded *request body* wherever the claim is "the model was told this",
because that is the wire, not this adapter's own account of it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any, cast

import pytest
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import errors, types
from inline_snapshot import snapshot
from vcr.cassette import Cassette

from logfire.agent_control.google_adk import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import Conversation, publish, run

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.vcr(),
    # These share the process-global `GOOGLE_API_KEY` set below and replay HTTP for one host, so
    # under CI's `--dist=loadgroup` they belong on one worker in collection order.
    pytest.mark.xdist_group(name='agent_control_google_adk_live'),
]

MODEL = 'gemini-2.5-flash-lite'
"""The cheapest current Gemini model, and the last generation to count thinking in tokens."""

THINKING_LEVEL_MODEL = 'gemini-3.5-flash-lite'
"""The cheapest current Gemini model of the generation that asks for thinking as a level."""


@pytest.fixture(autouse=True)
def _api_key() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """A key-shaped placeholder for replaying, and the recorder's own key when there is one.

    `google-genai` reads `GOOGLE_API_KEY` first and `GEMINI_API_KEY` second, and warns when both are
    set, so the placeholder is only filled in when neither is there: replaying needs no credentials,
    and re-recording picks up whichever of the two the recorder's environment carries. Scoped to the
    test rather than written at import, so it cannot decide what another module's own fallback
    resolves to when the two land on one xdist worker.
    """
    with pytest.MonkeyPatch.context() as monkeypatch:
        if not os.environ.get('GOOGLE_API_KEY') and not os.environ.get('GEMINI_API_KEY'):
            monkeypatch.setenv('GOOGLE_API_KEY', 'not-a-real-key')
        yield


def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f'It is 17 degrees and raining in {city}.'


def _requests(cassette: Cassette) -> list[Any]:
    """The requests this run made, recorded or replayed. `vcrpy` ships no type information."""
    return cast('list[Any]', cassette.requests)  # pyright: ignore[reportUnknownMemberType]


def request_bodies(cassette: Cassette) -> list[dict[str, Any]]:
    """What was actually sent, parsed."""
    return [json.loads(request.body) for request in _requests(cassette)]


def request_models(cassette: Cassette) -> list[str]:
    """Which model each request went to, off its path."""
    return [str(request.path).rsplit('/', 1)[-1] for request in _requests(cassette)]


def request_headers(cassette: Cassette) -> list[dict[str, str]]:
    """The headers each request carried, which is where a timeout rides rather than in the body."""
    return [dict(request.headers) for request in _requests(cassette)]


async def test_a_published_instruction_block_is_what_the_model_answers_from(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """The block reaches the wire as the system instruction, and the answer is the published one's."""
    publish(
        project,
        {
            'instructions': [
                {'id': 'agent', 'instructions': 'You are a pirate. Answer every question in one short sentence.'}
            ]
        },
    )
    agent = agent_control(
        LlmAgent(name='checkout', model=MODEL, instruction='You are a concise checkout assistant.'),
        label='production',
    )
    answer = ' '.join(await run(agent, 'Where is my refund?'))

    sent = request_bodies(vcr)[0]['systemInstruction']
    assert sent['parts'][0]['text'] == snapshot("""\
You are a pirate. Answer every question in one short sentence.

You are an agent. Your internal name is "checkout".\
""")
    assert 'concise checkout assistant' not in json.dumps(sent)
    assert answer == snapshot(
        "I be lookin' into yer refund, matey, and I'll have it sorted faster than a kraken can sink a galleon."
    )


async def test_a_renamed_tool_is_called_by_its_managed_name_and_dispatched_by_the_code_name(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """The whole of the rename claim, end to end against a model that actually decides to call it.

    The model is shown `lookup_forecast` and calls it; ADK dispatches to the code's `get_weather`;
    `before_tool_callback` -- the hook a deployment keys its approvals and its logging on -- is
    handed the tool under the name the code gave it; and the session persists that name too, which is
    what makes a rename safe to change halfway through a conversation.
    """
    publish(
        project,
        {
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'new_name': 'lookup_forecast',
                    'description': 'Look up the current forecast for a city.',
                    'parameters': {'city': {'description': "The city to look up, e.g. 'London'."}},
                }
            ]
        },
    )
    seen: list[str] = []

    def record_tool(tool: BaseTool, args: dict[str, Any], tool_context: ToolContext) -> None:
        seen.append(tool.name)

    agent = agent_control(
        LlmAgent(
            name='checkout',
            model=MODEL,
            instruction='Use your tools to answer. Give the answer in one short sentence.',
            tools=[get_weather],
            before_tool_callback=record_tool,
        ),
        label='production',
    )
    conversation = Conversation(agent)
    try:
        await conversation.turn('What is the weather in Paris?')
        persisted = await conversation.tool_names()
    finally:
        await conversation.close()

    first, second = request_bodies(vcr)
    # What the model was shown, and what it called back with.
    assert first['tools'] == snapshot(
        [
            {
                'functionDeclarations': [
                    {
                        'description': 'Look up the current forecast for a city.',
                        'name': 'lookup_forecast',
                        'parameters_json_schema': {
                            'properties': {
                                'city': {
                                    'title': 'City',
                                    'type': 'string',
                                    'description': "The city to look up, e.g. 'London'.",
                                }
                            },
                            'required': ['city'],
                            'title': 'get_weatherParams',
                            'type': 'object',
                        },
                    }
                ]
            }
        ]
    )
    replayed = [part for content in second['contents'] for part in content['parts']]
    assert [part['functionCall']['name'] for part in replayed if 'functionCall' in part] == snapshot(
        ['lookup_forecast']
    )
    responses = [part['functionResponse'] for part in replayed if 'functionResponse' in part]
    assert [response['name'] for response in responses] == snapshot(['lookup_forecast'])
    # The value the model was given back, which is what the *code's* `get_weather` returned: the
    # rename reached the model and the dispatch reached the implementation behind it.
    assert [response['response'] for response in responses] == snapshot(
        [{'result': 'It is 17 degrees and raining in Paris.'}]
    )
    # What this deployment's own code saw, which is the name it wrote.
    assert seen == snapshot(['get_weather'])
    assert persisted == snapshot(['get_weather', 'get_weather'])


async def test_a_reworded_parameter_description_is_what_the_model_fills_in(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """A description a plain Python function never had, added in Logfire, and obeyed on the wire."""
    publish(
        project,
        {
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'parameters': {'city': {'description': 'The city, always spelled in French.'}},
                }
            ]
        },
    )
    agent = agent_control(
        LlmAgent(
            name='checkout',
            model=MODEL,
            instruction='Use your tools to answer. Give the answer in one short sentence.',
            tools=[get_weather],
        ),
        label='production',
    )
    await run(agent, 'What is the weather in Cologne?')

    first, second = request_bodies(vcr)
    declaration = first['tools'][0]['functionDeclarations'][0]
    assert declaration['parameters_json_schema']['properties']['city']['description'] == snapshot(
        'The city, always spelled in French.'
    )
    called = [
        part['functionCall'] for content in second['contents'] for part in content['parts'] if 'functionCall' in part
    ]
    assert [call['args'] for call in called] == snapshot([{'city': 'Cologne'}])


async def test_every_setting_the_gemini_row_claims_is_accepted_by_the_api(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """The settings table, sent to the provider in one request rather than read off ADK's source.

    Every canonical setting `_GEMINI_SETTINGS` claims, published at once. A `200` is the claim; the
    recorded request body is what it is a claim *about*.
    """
    publish(
        project,
        {
            'settings': {
                'max_tokens': 256,
                'temperature': 0.2,
                'top_p': 0.9,
                'top_k': 20,
                'seed': 7,
                'stop_sequences': ['NEVERMIND'],
                'timeout': 30,
                'thinking': False,
            }
        },
    )
    agent = agent_control(LlmAgent(name='checkout', model=MODEL, instruction='Answer in one word.'), label='production')
    assert await run(agent, 'Say hello.') == snapshot(['Hello.'])

    assert request_bodies(vcr)[0]['generationConfig'] == snapshot(
        {
            'maxOutputTokens': 256,
            'seed': 7,
            'stopSequences': ['NEVERMIND'],
            'temperature': 0.2,
            'thinkingConfig': {'thinking_budget': 0},
            'topK': 20.0,
            'topP': 0.9,
        }
    )
    # `timeout` is the one setting that is not part of the generation config: `google-genai` lowers
    # `http_options.timeout` onto the request itself, in whole seconds.
    assert request_headers(vcr)[0]['X-Server-Timeout'] == snapshot('30')


async def test_a_gemini_2_model_asks_for_thinking_as_a_budget_and_a_gemini_3_model_as_a_level(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """`thinking: false` is spelled differently per generation, and each spelling is accepted."""
    publish(project, {'settings': {'thinking': False}})
    for model in (MODEL, THINKING_LEVEL_MODEL):
        agent = agent_control(
            LlmAgent(name='checkout', model=model, instruction='Answer in one word.'), label='production'
        )
        assert await run(agent, 'Say hello.') != []

    assert [body['generationConfig']['thinkingConfig'] for body in request_bodies(vcr)] == snapshot(
        [{'thinking_budget': 0}, {'thinking_level': 'MINIMAL'}]
    )


@pytest.mark.parametrize(
    ('model', 'thinking_config', 'message'),
    [
        pytest.param(
            MODEL,
            types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            'Thinking level is not supported',
            id='gemini_2_refuses_a_level',
        ),
        pytest.param(
            THINKING_LEVEL_MODEL,
            types.ThinkingConfig(thinking_budget=0),
            'invalid argument',
            id='gemini_3_refuses_a_zero_budget',
        ),
    ],
)
async def test_the_thinking_spelling_a_generation_does_not_take_fails_the_request(
    model: str, thinking_config: types.ThinkingConfig, message: str
) -> None:
    """Why `_settings` chooses per generation instead of sending one spelling to both.

    Sent through ADK's own client and around the adapter, because what is being recorded here is the
    provider's answer -- the thing the adapter exists to keep a published value from ever producing.
    """
    request = LlmRequest(
        model=model,
        contents=[types.Content(role='user', parts=[types.Part.from_text(text='Say hello.')])],
        config=types.GenerateContentConfig(max_output_tokens=2048, thinking_config=thinking_config),
    )
    with pytest.raises(errors.ClientError, match=message):
        async for _ in Gemini(model=model).generate_content_async(request):
            pass  # pragma: no cover - the request never reaches a response


async def test_a_penalty_fails_the_request_on_every_gemini_model() -> None:
    """Why `_GEMINI_SETTINGS` leaves the two penalties out even though ADK forwards them.

    `presence_penalty` and `frequency_penalty` are `GenerateContentConfig` fields, ADK hands the
    whole config to `google-genai`, and the API answers `400`. Recorded on the cheapest model; the
    same answer came back from `gemini-2.5-flash`, `gemini-2.5-pro` and `gemini-3.5-flash-lite`.
    """
    request = LlmRequest(
        model=MODEL,
        contents=[types.Content(role='user', parts=[types.Part.from_text(text='Say hello.')])],
        config=types.GenerateContentConfig(presence_penalty=0.1),
    )
    with pytest.raises(errors.ClientError, match='Penalty is not enabled'):
        async for _ in Gemini(model=MODEL).generate_content_async(request):
            pass  # pragma: no cover - the request never reaches a response


async def test_a_published_model_switch_is_the_model_the_request_goes_to(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """A canonical `google:` name, which is what Pydantic AI v2 calls the Gemini API."""
    publish(project, {'model': f'google:{THINKING_LEVEL_MODEL}'})
    agent = agent_control(LlmAgent(name='checkout', model=MODEL, instruction='Answer in one word.'), label='production')
    assert await run(agent, 'Say hello.') != []
    assert request_models(vcr) == snapshot(['gemini-3.5-flash-lite:generateContent'])


async def test_an_unmanaged_request_is_the_one_the_agent_would_have_sent(
    project: LocalVariableProvider, vcr: Cassette
) -> None:
    """Wrapping an agent nothing is published for changes no byte of what it sends."""

    def build(managed: bool) -> LlmAgent:
        agent = LlmAgent(
            name='checkout',
            model=MODEL,
            instruction='You are a concise checkout assistant.',
            tools=[get_weather],
            generate_content_config=types.GenerateContentConfig(temperature=0.1),
        )
        return agent_control(agent, label='production') if managed else agent

    await run(build(managed=True), 'Say hello.')
    await run(build(managed=False), 'Say hello.')
    managed_body, unmanaged_body = request_bodies(vcr)
    assert managed_body == unmanaged_body
