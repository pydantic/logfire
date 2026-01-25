from __future__ import annotations as _annotations

import json
from collections.abc import AsyncIterator, Iterator
from io import BytesIO
from typing import Any, cast

import httpx
import openai
import pydantic
import pytest
from dirty_equals import IsNumeric
from httpx._transports.mock import MockTransport
from inline_snapshot import snapshot
from openai.types import (
    completion,
    completion_choice,
    completion_usage,
    create_embedding_response,
    embedding,
    file_object,
    image,
    images_response,
)
from openai.types.chat import chat_completion, chat_completion_chunk as cc_chunk, chat_completion_message
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall, Function
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

import logfire
from logfire._internal.utils import get_version, suppress_instrumentation
from logfire.testing import TestExporter

pytestmark = [
    pytest.mark.skipif(
        get_version(pydantic.__version__) < get_version('2.5'),
        reason='Requires Pydantic 2.5 or higher to import genai-prices and set operation.cost attribute',
    ),
]


def request_handler(request: httpx.Request) -> httpx.Response:
    """Used to mock httpx requests

    We do this instead of using pytest-httpx since 1) it's nearly as simple 2) pytest-httpx doesn't support Python 3.8.
    (We no longer support 3.8 either, but it's not worth changing this now)
    """
    assert request.method == 'POST'
    if request.url == 'https://api.openai.com/v1/chat/completions':
        json_body = json.loads(request.content)
        if json_body.get('stream'):
            if json_body['messages'][0]['content'] == 'empty response chunk':
                return httpx.Response(200, text='data: []\n\n')
            elif json_body['messages'][0]['content'] == 'empty choices in response chunk':
                chunk = cc_chunk.ChatCompletionChunk(
                    id='1',
                    choices=[],
                    created=1,
                    model='gpt-4',
                    object='chat.completion.chunk',
                )
                return httpx.Response(200, text=f'data: {chunk.model_dump_json()}\n\n')
            elif json_body['messages'][0]['content'] == 'streamed tool call':
                chunks = [
                    cc_chunk.ChatCompletionChunk(
                        id='1',
                        choices=[
                            cc_chunk.Choice(
                                delta=cc_chunk.ChoiceDelta(
                                    role='assistant',
                                    tool_calls=[
                                        cc_chunk.ChoiceDeltaToolCall(
                                            index=0,
                                            id='1',
                                            function=cc_chunk.ChoiceDeltaToolCallFunction(
                                                arguments='', name='get_current_weather'
                                            ),
                                            type='function',
                                        )
                                    ],
                                ),
                                index=0,
                            )
                        ],
                        created=1,
                        model='gpt-4',
                        object='chat.completion.chunk',
                    ),
                    cc_chunk.ChatCompletionChunk(
                        id='1',
                        choices=[
                            cc_chunk.Choice(
                                delta=cc_chunk.ChoiceDelta(
                                    tool_calls=[
                                        cc_chunk.ChoiceDeltaToolCall(
                                            index=0, function=cc_chunk.ChoiceDeltaToolCallFunction(arguments='{"')
                                        )
                                    ]
                                ),
                                index=0,
                            )
                        ],
                        created=1,
                        model='gpt-4',
                        object='chat.completion.chunk',
                    ),
                    cc_chunk.ChatCompletionChunk(
                        id='1',
                        choices=[
                            cc_chunk.Choice(
                                delta=cc_chunk.ChoiceDelta(
                                    tool_calls=[
                                        cc_chunk.ChoiceDeltaToolCall(
                                            index=0, function=cc_chunk.ChoiceDeltaToolCallFunction(arguments='location')
                                        )
                                    ]
                                ),
                                index=0,
                            )
                        ],
                        created=1,
                        model='gpt-4',
                        object='chat.completion.chunk',
                    ),
                    cc_chunk.ChatCompletionChunk(
                        id='1',
                        choices=[
                            cc_chunk.Choice(
                                delta=cc_chunk.ChoiceDelta(
                                    tool_calls=[
                                        cc_chunk.ChoiceDeltaToolCall(
                                            index=0, function=cc_chunk.ChoiceDeltaToolCallFunction(arguments='":"')
                                        )
                                    ]
                                ),
                                index=0,
                            )
                        ],
                        created=1,
                        model='gpt-4',
                        object='chat.completion.chunk',
                    ),
                    cc_chunk.ChatCompletionChunk(
                        id='1',
                        choices=[
                            cc_chunk.Choice(
                                delta=cc_chunk.ChoiceDelta(
                                    tool_calls=[
                                        cc_chunk.ChoiceDeltaToolCall(
                                            index=0, function=cc_chunk.ChoiceDeltaToolCallFunction(arguments='Boston')
                                        )
                                    ]
                                ),
                                index=0,
                            )
                        ],
                        created=1,
                        model='gpt-4',
                        object='chat.completion.chunk',
                    ),
                    cc_chunk.ChatCompletionChunk(
                        id='1',
                        choices=[
                            cc_chunk.Choice(
                                delta=cc_chunk.ChoiceDelta(
                                    tool_calls=[
                                        cc_chunk.ChoiceDeltaToolCall(
                                            index=0, function=cc_chunk.ChoiceDeltaToolCallFunction(arguments='"}')
                                        )
                                    ]
                                ),
                                index=0,
                            )
                        ],
                        created=1,
                        model='gpt-4',
                        object='chat.completion.chunk',
                    ),
                    cc_chunk.ChatCompletionChunk(
                        id='1',
                        choices=[cc_chunk.Choice(delta=cc_chunk.ChoiceDelta(), finish_reason='stop', index=0)],
                        created=1,
                        model='gpt-4',
                        object='chat.completion.chunk',
                    ),
                    cc_chunk.ChatCompletionChunk(
                        id='1',
                        choices=[],
                        created=1,
                        model='gpt-4',
                        object='chat.completion.chunk',
                        usage=completion_usage.CompletionUsage(completion_tokens=1, prompt_tokens=2, total_tokens=3),
                    ),
                ]
                return httpx.Response(
                    200, text=''.join(f'data: {chunk.model_dump_json(exclude_unset=True)}\n\n' for chunk in chunks)
                )
            else:
                chunks = [
                    cc_chunk.ChatCompletionChunk(
                        id='1',
                        choices=[
                            cc_chunk.Choice(index=0, delta=cc_chunk.ChoiceDelta(content='The answer', role='assistant'))
                        ],
                        created=1,
                        model='gpt-4',
                        object='chat.completion.chunk',
                    ),
                    cc_chunk.ChatCompletionChunk(
                        id='2',
                        choices=[cc_chunk.Choice(index=0, delta=cc_chunk.ChoiceDelta(content=' is secret'))],
                        created=1,
                        model='gpt-4',
                        object='chat.completion.chunk',
                    ),
                    cc_chunk.ChatCompletionChunk(
                        id='3',
                        choices=[cc_chunk.Choice(index=0, delta=cc_chunk.ChoiceDelta(content=None))],
                        created=1,
                        model='gpt-4',
                        object='chat.completion.chunk',
                    ),
                ]
                return httpx.Response(200, text=''.join(f'data: {chunk.model_dump_json()}\n\n' for chunk in chunks))
        else:
            # Check for special test cases
            messages: list[dict[str, Any]] = json_body.get('messages', [])

            # Test case: response with tool_calls (to test convert_openai_response_to_semconv with tool_calls)
            if any(m.get('content') == 'call a function for me' for m in messages):
                return httpx.Response(
                    200,
                    json=chat_completion.ChatCompletion(
                        id='test_tool_call_response',
                        choices=[
                            chat_completion.Choice(
                                finish_reason='tool_calls',
                                index=0,
                                message=chat_completion_message.ChatCompletionMessage(
                                    content=None,
                                    role='assistant',
                                    tool_calls=[
                                        ChatCompletionMessageToolCall(
                                            id='call_xyz789',
                                            type='function',
                                            function=Function(
                                                name='get_weather',
                                                arguments='{"location": "San Francisco"}',
                                            ),
                                        ),
                                    ],
                                ),
                            ),
                        ],
                        created=1634720000,
                        model='gpt-4',
                        object='chat.completion',
                        usage=completion_usage.CompletionUsage(
                            completion_tokens=15,
                            prompt_tokens=25,
                            total_tokens=40,
                        ),
                    ).model_dump(mode='json'),
                )

            # Test case: tool call conversation (assistant with tool_calls + tool response)
            if any(m.get('role') == 'tool' for m in messages):
                return httpx.Response(
                    200,
                    json=chat_completion.ChatCompletion(
                        id='test_tool_response_id',
                        choices=[
                            chat_completion.Choice(
                                finish_reason='stop',
                                index=0,
                                message=chat_completion_message.ChatCompletionMessage(
                                    content='The weather in Boston is sunny and 72°F.',
                                    role='assistant',
                                ),
                            ),
                        ],
                        created=1634720000,
                        model='gpt-4',
                        object='chat.completion',
                        usage=completion_usage.CompletionUsage(
                            completion_tokens=10,
                            prompt_tokens=20,
                            total_tokens=30,
                        ),
                    ).model_dump(mode='json'),
                )

            # Test case: image content in message
            def has_image_content(msg: dict[str, Any]) -> bool:
                content = msg.get('content')
                if isinstance(content, list):
                    for part in cast(list[Any], content):
                        if isinstance(part, dict):
                            part_dict = cast(dict[str, Any], part)
                            if part_dict.get('type') == 'image_url':
                                return True
                return False

            if any(has_image_content(m) for m in messages):
                return httpx.Response(
                    200,
                    json=chat_completion.ChatCompletion(
                        id='test_image_id',
                        choices=[
                            chat_completion.Choice(
                                finish_reason='stop',
                                index=0,
                                message=chat_completion_message.ChatCompletionMessage(
                                    content='I can see a cat in the image.',
                                    role='assistant',
                                ),
                            ),
                        ],
                        created=1634720000,
                        model='gpt-4-vision-preview',
                        object='chat.completion',
                        usage=completion_usage.CompletionUsage(
                            completion_tokens=8,
                            prompt_tokens=100,
                            total_tokens=108,
                        ),
                    ).model_dump(mode='json'),
                )

            # Test case: no finish_reason
            # Use model_construct to bypass Pydantic validation (which rejects None for finish_reason)
            if any(m.get('content') == 'test no finish reason' for m in messages):
                return httpx.Response(
                    200,
                    json=chat_completion.ChatCompletion.model_construct(
                        id='test_id_no_finish',
                        choices=[
                            chat_completion.Choice.model_construct(
                                finish_reason=None,
                                index=0,
                                message=chat_completion_message.ChatCompletionMessage.model_construct(
                                    content='Nine',
                                    role='assistant',
                                ),
                            ),
                        ],
                        created=1634720000,
                        model='gpt-4',
                        object='chat.completion',
                        usage=completion_usage.CompletionUsage(
                            completion_tokens=1,
                            prompt_tokens=2,
                            total_tokens=3,
                        ),
                    ).model_dump(mode='json'),
                )

            # Default response
            return httpx.Response(
                200,
                json=chat_completion.ChatCompletion(
                    id='test_id',
                    choices=[
                        chat_completion.Choice(
                            finish_reason='stop',
                            index=0,
                            message=chat_completion_message.ChatCompletionMessage(
                                content='Nine',
                                role='assistant',
                            ),
                        ),
                    ],
                    created=1634720000,
                    model='gpt-4',
                    object='chat.completion',
                    usage=completion_usage.CompletionUsage(
                        completion_tokens=1,
                        prompt_tokens=2,
                        total_tokens=3,
                    ),
                ).model_dump(mode='json'),
            )
    elif request.url == 'https://api.openai.com/v1/completions':
        json_body = json.loads(request.content)
        if json_body.get('stream'):
            completion_chunks = [
                completion.Completion(
                    id='1',
                    # finish_reason is wrong, should be None
                    choices=[completion_choice.CompletionChoice(finish_reason='stop', index=0, text='The answer')],
                    created=1,
                    model='gpt-3.5-turbo-instruct',
                    object='text_completion',
                ),
                completion.Completion(
                    id='2',
                    choices=[completion_choice.CompletionChoice(finish_reason='stop', index=1, text=' is Nine')],
                    created=2,
                    model='gpt-3.5-turbo-instruct',
                    object='text_completion',
                ),
                completion.Completion(
                    id='3',
                    # finish_reason is wrong, should be None
                    choices=[completion_choice.CompletionChoice(finish_reason='stop', index=2, text='')],
                    created=3,
                    model='gpt-3.5-turbo-instruct',
                    object='text_completion',
                ),
            ]
            return httpx.Response(
                200, text=''.join(f'data: {chunk.model_dump_json()}\n\n' for chunk in completion_chunks)
            )
        else:
            # Test case: no finish_reason
            # Use model_construct to bypass Pydantic validation (which rejects None for finish_reason)
            if json_body.get('prompt') == 'test no finish reason':
                return httpx.Response(
                    200,
                    json=completion.Completion.model_construct(
                        id='test_id_no_finish',
                        choices=[
                            completion_choice.CompletionChoice.model_construct(finish_reason=None, index=0, text='Nine')
                        ],
                        created=123,
                        model='gpt-3.5-turbo-instruct',
                        object='text_completion',
                        usage=completion_usage.CompletionUsage(
                            completion_tokens=1,
                            prompt_tokens=2,
                            total_tokens=3,
                        ),
                    ).model_dump(mode='json'),
                )
            return httpx.Response(
                200,
                json=completion.Completion(
                    id='test_id',
                    choices=[completion_choice.CompletionChoice(finish_reason='stop', index=0, text='Nine')],
                    created=123,
                    model='gpt-3.5-turbo-instruct',
                    object='text_completion',
                    usage=completion_usage.CompletionUsage(
                        completion_tokens=1,
                        prompt_tokens=2,
                        total_tokens=3,
                    ),
                ).model_dump(mode='json'),
            )
    elif request.url == 'https://api.openai.com/v1/embeddings':
        return httpx.Response(
            200,
            json=create_embedding_response.CreateEmbeddingResponse(
                data=[
                    embedding.Embedding(
                        embedding=[1.0, 2.0, 3.0],
                        index=0,
                        object='embedding',
                    ),
                ],
                model='text-embedding-3-small',
                object='list',
                usage=create_embedding_response.Usage(
                    prompt_tokens=1,
                    total_tokens=2,
                ),
            ).model_dump(mode='json'),
        )
    elif request.url == 'https://api.openai.com/v1/images/generations':
        return httpx.Response(
            200,
            json=images_response.ImagesResponse(
                created=123,
                data=[
                    image.Image(
                        revised_prompt='revised prompt',
                        url='https://example.com/image.jpg',
                    ),
                ],
            ).model_dump(mode='json'),
        )
    elif request.url == 'https://api.openai.com/v1/files':
        return httpx.Response(
            200,
            json=file_object.FileObject(
                id='test_id',
                bytes=42,
                created_at=123,
                filename='test.txt',
                object='file',
                purpose='fine-tune',
                status='uploaded',
            ).model_dump(mode='json'),
        )
    elif request.url == 'https://api.openai.com/v1/assistants':
        return httpx.Response(
            200,
            json={
                'id': 'asst_abc123',
                'object': 'assistant',
                'created_at': 1698984975,
                'name': 'Math Tutor',
                'description': None,
                'model': 'gpt-4-turbo',
                'instructions': 'You are a personal math tutor. When asked a question, write and run Python code to answer the question.',
                'tools': [{'type': 'code_interpreter'}],
                'metadata': {},
                'top_p': 1.0,
                'temperature': 1.0,
                'response_format': 'auto',
            },
        )
    elif request.url == 'https://api.openai.com/v1/threads':
        return httpx.Response(
            200,
            json={'id': 'thread_abc123', 'object': 'thread', 'created_at': 1698107661, 'metadata': {}},
        )
    elif request.url == 'https://api.openai.com/v1/responses':
        json_body = json.loads(request.content)
        # Return a simple response for the responses API
        return httpx.Response(
            200,
            json={
                'id': 'resp_test123',
                'object': 'response',
                'created_at': 1698107661,
                'status': 'completed',
                'background': False,
                'billing': {'payer': 'developer'},
                'error': None,
                'incomplete_details': None,
                'instructions': json_body.get('instructions'),
                'max_output_tokens': None,
                'max_tool_calls': None,
                'model': json_body.get('model', 'gpt-4.1'),
                'output': [
                    {
                        'id': 'msg_test123',
                        'type': 'message',
                        'status': 'completed',
                        'role': 'assistant',
                        'content': [
                            {
                                'type': 'output_text',
                                'text': 'Nine',
                                'annotations': [],
                            }
                        ],
                    }
                ],
                'parallel_tool_calls': True,
                'previous_response_id': None,
                'prompt_cache_key': None,
                'reasoning': {'effort': None, 'summary': None},
                'safety_identifier': None,
                'service_tier': 'default',
                'store': True,
                'temperature': 1.0,
                'text': {'format': {'type': 'text'}, 'verbosity': 'medium'},
                'tool_choice': 'auto',
                'tools': [],
                'top_logprobs': 0,
                'top_p': 1.0,
                'truncation': 'disabled',
                'usage': {
                    'input_tokens': 10,
                    'input_tokens_details': {'cached_tokens': 0},
                    'output_tokens': 1,
                    'output_tokens_details': {'reasoning_tokens': 0},
                    'total_tokens': 11,
                },
                'user': None,
                'metadata': {},
            },
        )
    else:  # pragma: no cover
        raise ValueError(f'Unexpected request to {request.url!r}')


@pytest.fixture
def instrumented_client() -> Iterator[openai.Client]:
    with httpx.Client(transport=MockTransport(request_handler)) as httpx_client:
        # use a hardcoded API key to make sure one in the environment is never used
        openai_client = openai.Client(api_key='foobar', http_client=httpx_client)

        # Test instrumenting a class
        with logfire.instrument_openai(openai.Client):
            # Test repeatedly instrumenting something already instrumented (should do nothing)
            with logfire.instrument_openai(openai.Client):
                pass
            with logfire.instrument_openai(openai_client):
                pass

            yield openai_client


@pytest.fixture
async def instrumented_async_client() -> AsyncIterator[openai.AsyncClient]:
    async with httpx.AsyncClient(transport=MockTransport(request_handler)) as httpx_client:
        # use a hardcoded API key to make sure one in the environment is never used
        openai_client = openai.AsyncClient(api_key='foobar', http_client=httpx_client)

        with logfire.instrument_openai(openai_client):
            yield openai_client


def test_sync_chat_completions(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    response = instrumented_client.chat.completions.create(
        model='gpt-4',
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': 'What is four plus five?'},
        ],
    )
    assert response.choices[0].message.content == 'Nine'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_sync_chat_completions',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [
                            {'role': 'system', 'content': 'You are a helpful assistant.'},
                            {'role': 'user', 'content': 'What is four plus five?'},
                        ],
                        'model': 'gpt-4',
                    },
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.operation.name': 'chat',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'gen_ai.system': 'openai',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'gpt-4',
                    'operation.cost': 0.00012,
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'response_data': {
                        'message': {
                            'content': 'Nine',
                            'refusal': None,
                            'audio': None,
                            'annotations': None,
                            'role': 'assistant',
                            'function_call': None,
                            'tool_calls': None,
                        },
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}], 'finish_reason': 'stop'}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.system': {},
                            'async': {},
                            'gen_ai.response.model': {},
                            'operation.cost': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ChatCompletionMessage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


def test_sync_chat_completions_with_all_request_params(
    instrumented_client: openai.Client, exporter: TestExporter
) -> None:
    """Test that all optional request parameters are extracted to span attributes."""
    response = instrumented_client.chat.completions.create(
        model='gpt-4',
        messages=[
            {'role': 'user', 'content': 'What is four plus five?'},
        ],
        max_tokens=100,
        temperature=0.7,
        top_p=0.9,
        stop=['END', 'STOP'],
        seed=42,
        frequency_penalty=0.5,
        presence_penalty=0.3,
    )
    assert response.choices[0].message.content == 'Nine'
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert spans == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_sync_chat_completions_with_all_request_params',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'user', 'content': 'What is four plus five?'}],
                        'model': 'gpt-4',
                        'frequency_penalty': 0.5,
                        'max_tokens': 100,
                        'presence_penalty': 0.3,
                        'seed': 42,
                        'stop': ['END', 'STOP'],
                        'temperature': 0.7,
                        'top_p': 0.9,
                    },
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.max_tokens': 100,
                    'gen_ai.request.temperature': 0.7,
                    'gen_ai.request.top_p': 0.9,
                    'gen_ai.request.stop_sequences': ['END', 'STOP'],
                    'gen_ai.request.seed': 42,
                    'gen_ai.request.frequency_penalty': 0.5,
                    'gen_ai.request.presence_penalty': 0.3,
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-4',
                    'operation.cost': 0.00012,
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'response_data': {
                        'message': {
                            'content': 'Nine',
                            'refusal': None,
                            'role': 'assistant',
                            'annotations': None,
                            'audio': None,
                            'function_call': None,
                            'tool_calls': None,
                        },
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}], 'finish_reason': 'stop'}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.request.max_tokens': {},
                            'gen_ai.request.temperature': {},
                            'gen_ai.request.top_p': {},
                            'gen_ai.request.stop_sequences': {},
                            'gen_ai.request.seed': {},
                            'gen_ai.request.frequency_penalty': {},
                            'gen_ai.request.presence_penalty': {},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'operation.cost': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ChatCompletionMessage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


def test_sync_chat_completions_with_stop_string(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    """Test that stop as a string is properly converted to JSON array."""
    response = instrumented_client.chat.completions.create(
        model='gpt-4',
        messages=[
            {'role': 'user', 'content': 'What is four plus five?'},
        ],
        stop='END',
    )
    assert response.choices[0].message.content == 'Nine'
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert spans == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_sync_chat_completions_with_stop_string',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'user', 'content': 'What is four plus five?'}],
                        'model': 'gpt-4',
                        'stop': 'END',
                    },
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.stop_sequences': ['END'],
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-4',
                    'operation.cost': 0.00012,
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'response_data': {
                        'message': {
                            'content': 'Nine',
                            'refusal': None,
                            'role': 'assistant',
                            'annotations': None,
                            'audio': None,
                            'function_call': None,
                            'tool_calls': None,
                        },
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}], 'finish_reason': 'stop'}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.request.stop_sequences': {},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'operation.cost': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ChatCompletionMessage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


def test_extract_request_parameters_max_output_tokens() -> None:
    """Test that max_output_tokens is extracted when max_tokens is absent.

    The Responses API uses max_output_tokens instead of max_tokens.
    """
    from logfire._internal.integrations.llm_providers.openai import (
        _extract_request_parameters,  # pyright: ignore[reportPrivateUsage]
    )

    json_data: dict[str, Any] = {'max_output_tokens': 200}
    span_data: dict[str, Any] = {}
    _extract_request_parameters(json_data, span_data)
    assert span_data['gen_ai.request.max_tokens'] == 200


async def test_async_chat_completions(instrumented_async_client: openai.AsyncClient, exporter: TestExporter) -> None:
    response = await instrumented_async_client.chat.completions.create(
        model='gpt-4',
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': 'What is four plus five?'},
        ],
    )
    assert response.choices[0].message.content == 'Nine'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_async_chat_completions',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [
                            {'role': 'system', 'content': 'You are a helpful assistant.'},
                            {'role': 'user', 'content': 'What is four plus five?'},
                        ],
                        'model': 'gpt-4',
                    },
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.operation.name': 'chat',
                    'async': True,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'gen_ai.system': 'openai',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'gpt-4',
                    'operation.cost': 0.00012,
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'response_data': {
                        'message': {
                            'content': 'Nine',
                            'refusal': None,
                            'audio': None,
                            'annotations': None,
                            'role': 'assistant',
                            'function_call': None,
                            'tool_calls': None,
                        },
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}], 'finish_reason': 'stop'}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.system': {},
                            'async': {},
                            'gen_ai.response.model': {},
                            'operation.cost': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ChatCompletionMessage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


def test_sync_chat_empty_response_chunk(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    response = instrumented_client.chat.completions.create(
        model='gpt-4',
        messages=[{'role': 'system', 'content': 'empty response chunk'}],
        stream=True,
    )
    combined = [chunk for chunk in response]
    assert combined == [[]]
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_sync_chat_empty_response_chunk',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'system', 'content': 'empty response chunk'}],
                        'model': 'gpt-4',
                        'stream': True,
                    },
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.operation.name': 'chat',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                        },
                    },
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'gpt-4',
                },
            },
            {
                'name': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.level_num': 9,
                    'request_data': {
                        'messages': [{'role': 'system', 'content': 'empty response chunk'}],
                        'model': 'gpt-4',
                        'stream': True,
                    },
                    'async': False,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_sync_chat_empty_response_chunk',
                    'code.lineno': 123,
                    'logfire.msg': "streaming response from 'gpt-4' took 1.00s",
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.provider.name': 'openai',
                    'logfire.span_type': 'log',
                    'gen_ai.operation.name': 'chat',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': {'combined_chunk_content': '', 'chunk_count': 0},
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'duration': {},
                            'response_data': {'type': 'object'},
                        },
                    },
                    'gen_ai.response.model': 'gpt-4',
                },
            },
        ]
    )


def test_sync_chat_empty_response_choices(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    response = instrumented_client.chat.completions.create(
        model='gpt-4',
        messages=[{'role': 'system', 'content': 'empty choices in response chunk'}],
        stream=True,
    )
    combined = [chunk for chunk in response]
    assert len(combined) == 1
    assert combined[0].choices == []
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_sync_chat_empty_response_choices',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'system', 'content': 'empty choices in response chunk'}],
                        'model': 'gpt-4',
                        'stream': True,
                    },
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.operation.name': 'chat',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                        },
                    },
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'gpt-4',
                },
            },
            {
                'name': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.level_num': 9,
                    'request_data': {
                        'messages': [{'role': 'system', 'content': 'empty choices in response chunk'}],
                        'model': 'gpt-4',
                        'stream': True,
                    },
                    'async': False,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_sync_chat_empty_response_choices',
                    'code.lineno': 123,
                    'logfire.msg': "streaming response from 'gpt-4' took 1.00s",
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.provider.name': 'openai',
                    'logfire.span_type': 'log',
                    'gen_ai.operation.name': 'chat',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': {'message': None, 'usage': None},
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'duration': {},
                            'response_data': {'type': 'object'},
                        },
                    },
                    'gen_ai.response.model': 'gpt-4',
                },
            },
        ]
    )


def test_sync_chat_tool_call_stream(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    response = instrumented_client.chat.completions.create(
        model='gpt-4',
        messages=[{'role': 'system', 'content': 'streamed tool call'}],
        stream=True,
        stream_options={'include_usage': True},
        tool_choice={'type': 'function', 'function': {'name': 'get_current_weather'}},
        tools=[
            {
                'type': 'function',
                'function': {
                    'name': 'get_current_weather',
                    'description': 'Get the current weather in a given location',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'location': {
                                'type': 'string',
                                'description': 'The city and state, e.g. San Francisco, CA',
                            },
                            'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                        },
                        'required': ['location'],
                    },
                },
            },
        ],
    )
    combined_arguments = ''.join(
        chunk.choices[0].delta.tool_calls[0].function.arguments
        for chunk in response
        if chunk.choices
        and chunk.choices[0].delta.tool_calls
        and chunk.choices[0].delta.tool_calls[0].function
        and chunk.choices[0].delta.tool_calls[0].function.arguments
    )
    assert combined_arguments == '{"location":"Boston"}'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_sync_chat_tool_call_stream',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'system', 'content': 'streamed tool call'}],
                        'model': 'gpt-4',
                        'stream': True,
                        'stream_options': {'include_usage': True},
                        'tool_choice': {'type': 'function', 'function': {'name': 'get_current_weather'}},
                        'tools': [
                            {
                                'type': 'function',
                                'function': {
                                    'name': 'get_current_weather',
                                    'description': 'Get the current weather in a given location',
                                    'parameters': {
                                        'type': 'object',
                                        'properties': {
                                            'location': {
                                                'type': 'string',
                                                'description': 'The city and state, e.g. San Francisco, CA',
                                            },
                                            'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                                        },
                                        'required': ['location'],
                                    },
                                },
                            }
                        ],
                    },
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.tool.definitions': [
                        {
                            'type': 'function',
                            'function': {
                                'name': 'get_current_weather',
                                'description': 'Get the current weather in a given location',
                                'parameters': {
                                    'type': 'object',
                                    'properties': {
                                        'location': {
                                            'type': 'string',
                                            'description': 'The city and state, e.g. San Francisco, CA',
                                        },
                                        'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                                    },
                                    'required': ['location'],
                                },
                            },
                        }
                    ],
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.tool.definitions': {},
                            'async': {},
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.response.model': 'gpt-4',
                },
            },
            {
                'name': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'logfire.msg': "streaming response from 'gpt-4' took 1.00s",
                    'code.filepath': 'test_openai.py',
                    'code.function': '<genexpr>',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'system', 'content': 'streamed tool call'}],
                        'model': 'gpt-4',
                        'stream': True,
                        'stream_options': {'include_usage': True},
                        'tool_choice': {'type': 'function', 'function': {'name': 'get_current_weather'}},
                        'tools': [
                            {
                                'type': 'function',
                                'function': {
                                    'name': 'get_current_weather',
                                    'description': 'Get the current weather in a given location',
                                    'parameters': {
                                        'type': 'object',
                                        'properties': {
                                            'location': {
                                                'type': 'string',
                                                'description': 'The city and state, e.g. San Francisco, CA',
                                            },
                                            'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                                        },
                                        'required': ['location'],
                                    },
                                },
                            }
                        ],
                    },
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.provider.name': 'openai',
                    'async': False,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.tool.definitions': [
                        {
                            'type': 'function',
                            'function': {
                                'name': 'get_current_weather',
                                'description': 'Get the current weather in a given location',
                                'parameters': {
                                    'type': 'object',
                                    'properties': {
                                        'location': {
                                            'type': 'string',
                                            'description': 'The city and state, e.g. San Francisco, CA',
                                        },
                                        'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                                    },
                                    'required': ['location'],
                                },
                            },
                        }
                    ],
                    'duration': 1.0,
                    'response_data': {
                        'message': {
                            'content': None,
                            'refusal': None,
                            'role': 'assistant',
                            'annotations': None,
                            'audio': None,
                            'function_call': None,
                            'tool_calls': [
                                {
                                    'id': '1',
                                    'function': {
                                        'arguments': '{"location":"Boston"}',
                                        'name': 'get_current_weather',
                                        'parsed_arguments': None,
                                    },
                                    'type': 'function',
                                    'index': 0,
                                }
                            ],
                            'parsed': None,
                        },
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.tool.definitions': {},
                            'duration': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ParsedChatCompletionMessage[object]',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'tool_calls': {
                                                'type': 'array',
                                                'items': {
                                                    'type': 'object',
                                                    'title': 'ParsedFunctionToolCall',
                                                    'x-python-datatype': 'PydanticModel',
                                                    'properties': {
                                                        'function': {
                                                            'type': 'object',
                                                            'title': 'ParsedFunction',
                                                            'x-python-datatype': 'PydanticModel',
                                                        }
                                                    },
                                                },
                                            }
                                        },
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'gpt-4',
                },
            },
        ]
    )


async def test_async_chat_tool_call_stream(
    instrumented_async_client: openai.AsyncClient, exporter: TestExporter
) -> None:
    response = await instrumented_async_client.chat.completions.create(
        model='gpt-4',
        messages=[{'role': 'system', 'content': 'streamed tool call'}],
        stream=True,
        stream_options={'include_usage': True},
        tool_choice={'type': 'function', 'function': {'name': 'get_current_weather'}},
        tools=[
            {
                'type': 'function',
                'function': {
                    'name': 'get_current_weather',
                    'description': 'Get the current weather in a given location',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'location': {
                                'type': 'string',
                                'description': 'The city and state, e.g. San Francisco, CA',
                            },
                            'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                        },
                        'required': ['location'],
                    },
                },
            },
        ],
    )
    combined_arguments = ''.join(
        [
            chunk.choices[0].delta.tool_calls[0].function.arguments
            async for chunk in response
            if chunk.choices
            and chunk.choices[0].delta.tool_calls
            and chunk.choices[0].delta.tool_calls[0].function
            and chunk.choices[0].delta.tool_calls[0].function.arguments
        ]
    )
    assert combined_arguments == '{"location":"Boston"}'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_async_chat_tool_call_stream',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'system', 'content': 'streamed tool call'}],
                        'model': 'gpt-4',
                        'stream': True,
                        'stream_options': {'include_usage': True},
                        'tool_choice': {'type': 'function', 'function': {'name': 'get_current_weather'}},
                        'tools': [
                            {
                                'type': 'function',
                                'function': {
                                    'name': 'get_current_weather',
                                    'description': 'Get the current weather in a given location',
                                    'parameters': {
                                        'type': 'object',
                                        'properties': {
                                            'location': {
                                                'type': 'string',
                                                'description': 'The city and state, e.g. San Francisco, CA',
                                            },
                                            'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                                        },
                                        'required': ['location'],
                                    },
                                },
                            }
                        ],
                    },
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.tool.definitions': [
                        {
                            'type': 'function',
                            'function': {
                                'name': 'get_current_weather',
                                'description': 'Get the current weather in a given location',
                                'parameters': {
                                    'type': 'object',
                                    'properties': {
                                        'location': {
                                            'type': 'string',
                                            'description': 'The city and state, e.g. San Francisco, CA',
                                        },
                                        'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                                    },
                                    'required': ['location'],
                                },
                            },
                        }
                    ],
                    'async': True,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.tool.definitions': {},
                            'async': {},
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.response.model': 'gpt-4',
                },
            },
            {
                'name': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'logfire.msg': "streaming response from 'gpt-4' took 1.00s",
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_async_chat_tool_call_stream',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'system', 'content': 'streamed tool call'}],
                        'model': 'gpt-4',
                        'stream': True,
                        'stream_options': {'include_usage': True},
                        'tool_choice': {'type': 'function', 'function': {'name': 'get_current_weather'}},
                        'tools': [
                            {
                                'type': 'function',
                                'function': {
                                    'name': 'get_current_weather',
                                    'description': 'Get the current weather in a given location',
                                    'parameters': {
                                        'type': 'object',
                                        'properties': {
                                            'location': {
                                                'type': 'string',
                                                'description': 'The city and state, e.g. San Francisco, CA',
                                            },
                                            'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                                        },
                                        'required': ['location'],
                                    },
                                },
                            }
                        ],
                    },
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.provider.name': 'openai',
                    'async': True,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.tool.definitions': [
                        {
                            'type': 'function',
                            'function': {
                                'name': 'get_current_weather',
                                'description': 'Get the current weather in a given location',
                                'parameters': {
                                    'type': 'object',
                                    'properties': {
                                        'location': {
                                            'type': 'string',
                                            'description': 'The city and state, e.g. San Francisco, CA',
                                        },
                                        'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                                    },
                                    'required': ['location'],
                                },
                            },
                        }
                    ],
                    'duration': 1.0,
                    'response_data': {
                        'message': {
                            'content': None,
                            'refusal': None,
                            'role': 'assistant',
                            'annotations': None,
                            'audio': None,
                            'function_call': None,
                            'tool_calls': [
                                {
                                    'id': '1',
                                    'function': {
                                        'arguments': '{"location":"Boston"}',
                                        'name': 'get_current_weather',
                                        'parsed_arguments': None,
                                    },
                                    'type': 'function',
                                    'index': 0,
                                }
                            ],
                            'parsed': None,
                        },
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.tool.definitions': {},
                            'duration': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ParsedChatCompletionMessage[object]',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'tool_calls': {
                                                'type': 'array',
                                                'items': {
                                                    'type': 'object',
                                                    'title': 'ParsedFunctionToolCall',
                                                    'x-python-datatype': 'PydanticModel',
                                                    'properties': {
                                                        'function': {
                                                            'type': 'object',
                                                            'title': 'ParsedFunction',
                                                            'x-python-datatype': 'PydanticModel',
                                                        }
                                                    },
                                                },
                                            }
                                        },
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'gpt-4',
                },
            },
        ]
    )


def test_sync_chat_completions_stream(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    response = instrumented_client.chat.completions.create(
        model='gpt-4',
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': 'What is four plus five?'},
        ],
        stream=True,
    )
    combined = ''.join(chunk.choices[0].delta.content for chunk in response if chunk.choices[0].delta.content)
    assert combined == 'The answer is secret'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_sync_chat_completions_stream',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [
                            {'role': 'system', 'content': 'You are a helpful assistant.'},
                            {'role': 'user', 'content': 'What is four plus five?'},
                        ],
                        'model': 'gpt-4',
                        'stream': True,
                    },
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.operation.name': 'chat',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                        },
                    },
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'gpt-4',
                },
            },
            {
                'name': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.level_num': 9,
                    'request_data': {
                        'messages': [
                            {'role': 'system', 'content': 'You are a helpful assistant.'},
                            {'role': 'user', 'content': 'What is four plus five?'},
                        ],
                        'model': 'gpt-4',
                        'stream': True,
                    },
                    'async': False,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'code.filepath': 'test_openai.py',
                    'code.function': '<genexpr>',
                    'code.lineno': 123,
                    'logfire.msg': "streaming response from 'gpt-4' took 1.00s",
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.provider.name': 'openai',
                    'logfire.span_type': 'log',
                    'gen_ai.operation.name': 'chat',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': {
                        'message': {
                            'content': 'The answer is secret',
                            'refusal': None,
                            'role': 'assistant',
                            'annotations': None,
                            'audio': None,
                            'function_call': None,
                            'tool_calls': None,
                            'parsed': None,
                        },
                        'usage': None,
                    },
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'duration': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ParsedChatCompletionMessage[object]',
                                        'x-python-datatype': 'PydanticModel',
                                    }
                                },
                            },
                        },
                    },
                    'gen_ai.response.model': 'gpt-4',
                },
            },
        ]
    )


async def test_async_chat_completions_stream(
    instrumented_async_client: openai.AsyncClient, exporter: TestExporter
) -> None:
    response = await instrumented_async_client.chat.completions.create(
        model='gpt-4',
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': 'What is four plus five?'},
        ],
        stream=True,
    )
    chunk_content = [chunk.choices[0].delta.content async for chunk in response if chunk.choices[0].delta.content]
    combined = ''.join(chunk_content)
    assert combined == 'The answer is secret'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_async_chat_completions_stream',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [
                            {'role': 'system', 'content': 'You are a helpful assistant.'},
                            {'role': 'user', 'content': 'What is four plus five?'},
                        ],
                        'model': 'gpt-4',
                        'stream': True,
                    },
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.operation.name': 'chat',
                    'async': True,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                        },
                    },
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'gpt-4',
                },
            },
            {
                'name': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.level_num': 9,
                    'request_data': {
                        'messages': [
                            {'role': 'system', 'content': 'You are a helpful assistant.'},
                            {'role': 'user', 'content': 'What is four plus five?'},
                        ],
                        'model': 'gpt-4',
                        'stream': True,
                    },
                    'async': True,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_async_chat_completions_stream',
                    'code.lineno': 123,
                    'logfire.msg': "streaming response from 'gpt-4' took 1.00s",
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.provider.name': 'openai',
                    'logfire.span_type': 'log',
                    'gen_ai.operation.name': 'chat',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': {
                        'message': {
                            'content': 'The answer is secret',
                            'refusal': None,
                            'role': 'assistant',
                            'annotations': None,
                            'audio': None,
                            'function_call': None,
                            'tool_calls': None,
                            'parsed': None,
                        },
                        'usage': None,
                    },
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'duration': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ParsedChatCompletionMessage[object]',
                                        'x-python-datatype': 'PydanticModel',
                                    }
                                },
                            },
                        },
                    },
                    'gen_ai.response.model': 'gpt-4',
                },
            },
        ]
    )


def test_completions(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    response = instrumented_client.completions.create(
        model='gpt-3.5-turbo-instruct',
        prompt='What is four plus five?',
    )
    assert response.choices[0].text == 'Nine'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_completions',
                    'code.lineno': 123,
                    'request_data': {'model': 'gpt-3.5-turbo-instruct', 'prompt': 'What is four plus five?'},
                    'gen_ai.provider.name': 'openai',
                    'async': False,
                    'gen_ai.operation.name': 'text_completion',
                    'logfire.msg_template': 'Completion with {request_data[model]!r}',
                    'logfire.msg': "Completion with 'gpt-3.5-turbo-instruct'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.response.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'operation.cost': 5e-06,
                    'response_data': {
                        'finish_reason': 'stop',
                        'text': 'Nine',
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}], 'finish_reason': 'stop'}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.system': {},
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'operation.cost': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    }
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


@pytest.mark.vcr()
def test_responses_stream(exporter: TestExporter) -> None:
    client = openai.Client()
    logfire.instrument_openai(client)
    with client.responses.stream(
        model='gpt-4.1',
        input='What is four plus five?',
    ) as stream:
        for _ in stream:
            pass

        final_response = stream.get_final_response()

    assert final_response.output_text == snapshot('Four plus five equals **nine**.')
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_responses_stream',
                    'code.lineno': 123,
                    'gen_ai.provider.name': 'openai',
                    'events': [
                        {'event.name': 'gen_ai.user.message', 'content': 'What is four plus five?', 'role': 'user'}
                    ],
                    'request_data': {'model': 'gpt-4.1', 'stream': True},
                    'gen_ai.request.model': 'gpt-4.1',
                    'gen_ai.operation.name': 'chat',
                    'async': False,
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.msg': "Responses API with 'gpt-4.1'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.provider.name': {},
                            'events': {'type': 'array'},
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.response.model': 'gpt-4.1',
                },
            },
            {
                'name': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'logfire.msg': "streaming response from 'gpt-4.1' took 1.00s",
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_responses_stream',
                    'code.lineno': 123,
                    'request_data': {'model': 'gpt-4.1', 'stream': True},
                    'gen_ai.provider.name': 'openai',
                    'events': [
                        {'event.name': 'gen_ai.user.message', 'content': 'What is four plus five?', 'role': 'user'},
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'content': 'Four plus five equals **nine**.',
                            'role': 'assistant',
                        },
                    ],
                    'gen_ai.request.model': 'gpt-4.1',
                    'async': False,
                    'gen_ai.operation.name': 'chat',
                    'duration': 1.0,
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Four plus five equals **nine**.'}]}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'events': {'type': 'array'},
                            'gen_ai.request.model': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'duration': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'gpt-4.1',
                },
            },
        ]
    )


def test_completions_stream(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    response = instrumented_client.completions.create(
        model='gpt-3.5-turbo-instruct',
        prompt='What is four plus five?',
        stream=True,
    )
    combined = ''.join(chunk.choices[0].text for chunk in response if chunk.choices[0].text)
    assert combined == 'The answer is Nine'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_completions_stream',
                    'code.lineno': 123,
                    'request_data': {
                        'model': 'gpt-3.5-turbo-instruct',
                        'prompt': 'What is four plus five?',
                        'stream': True,
                    },
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.operation.name': 'text_completion',
                    'async': False,
                    'logfire.msg_template': 'Completion with {request_data[model]!r}',
                    'logfire.msg': "Completion with 'gpt-3.5-turbo-instruct'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                        },
                    },
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'gpt-3.5-turbo-instruct',
                },
            },
            {
                'name': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.level_num': 9,
                    'request_data': {
                        'model': 'gpt-3.5-turbo-instruct',
                        'prompt': 'What is four plus five?',
                        'stream': True,
                    },
                    'async': False,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'code.filepath': 'test_openai.py',
                    'code.function': '<genexpr>',
                    'code.lineno': 123,
                    'logfire.msg': "streaming response from 'gpt-3.5-turbo-instruct' took 1.00s",
                    'gen_ai.request.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.provider.name': 'openai',
                    'logfire.span_type': 'log',
                    'gen_ai.operation.name': 'text_completion',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': {'combined_chunk_content': 'The answer is Nine', 'chunk_count': 2},
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'duration': {},
                            'response_data': {'type': 'object'},
                        },
                    },
                    'gen_ai.response.model': 'gpt-3.5-turbo-instruct',
                },
            },
        ]
    )


def test_embeddings(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    response = instrumented_client.embeddings.create(
        input='This is a sentence to embed.',
        model='text-embedding-3-small',
    )
    assert response.data[0].embedding == [1.0, 2.0, 3.0]
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Embedding Creation with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_embeddings',
                    'code.lineno': 123,
                    'request_data': {
                        'input': 'This is a sentence to embed.',
                        'model': 'text-embedding-3-small',
                        'encoding_format': 'base64',
                    },
                    'gen_ai.provider.name': 'openai',
                    'async': False,
                    'gen_ai.operation.name': 'embeddings',
                    'logfire.msg_template': 'Embedding Creation with {request_data[model]!r}',
                    'logfire.msg': "Embedding Creation with 'text-embedding-3-small'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'text-embedding-3-small',
                    'gen_ai.response.model': 'text-embedding-3-small',
                    'gen_ai.usage.input_tokens': 1,
                    'response_data': {'usage': {'prompt_tokens': 1, 'total_tokens': 2}},
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.system': {},
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
                            'gen_ai.usage.input_tokens': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'usage': {'type': 'object', 'title': 'Usage', 'x-python-datatype': 'PydanticModel'}
                                },
                            },
                        },
                    },
                },
            }
        ]
    )


def test_images(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    response = instrumented_client.images.generate(
        model='dall-e-3',
        prompt='A picture of a cat.',
    )
    assert response.data
    assert response.data[0].revised_prompt == 'revised prompt'
    assert response.data[0].url == 'https://example.com/image.jpg'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Image Generation with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_images',
                    'code.lineno': 123,
                    'request_data': {'prompt': 'A picture of a cat.', 'model': 'dall-e-3'},
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'dall-e-3',
                    'gen_ai.operation.name': 'image_generation',
                    'async': False,
                    'logfire.msg_template': 'Image Generation with {request_data[model]!r}',
                    'logfire.msg': "Image Generation with 'dall-e-3'",
                    'logfire.span_type': 'span',
                    'gen_ai.system': 'openai',
                    'logfire.tags': ('LLM',),
                    'response_data': {
                        'images': [
                            {
                                'b64_json': None,
                                'revised_prompt': 'revised prompt',
                                'url': 'https://example.com/image.jpg',
                            }
                        ]
                    },
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.system': {},
                            'async': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'images': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'Image',
                                            'x-python-datatype': 'PydanticModel',
                                        },
                                    }
                                },
                            },
                        },
                    },
                    'gen_ai.response.model': 'dall-e-3',
                },
            }
        ]
    )


def test_dont_suppress_httpx(exporter: TestExporter) -> None:
    with httpx.Client(transport=MockTransport(request_handler)) as httpx_client:
        HTTPXClientInstrumentor().instrument_client(httpx_client)
        # use a hardcoded API key to make sure one in the environment is never used
        openai_client = openai.Client(api_key='foobar', http_client=httpx_client)

        with logfire.instrument_openai(openai_client, suppress_other_instrumentation=False):
            response = openai_client.completions.create(model='gpt-3.5-turbo-instruct', prompt='xxx')

    assert response.choices[0].text == 'Nine'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True, include_instrumentation_scope=True) == snapshot(
        [
            {
                'name': 'POST',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'instrumentation_scope': 'opentelemetry.instrumentation.httpx',
                'attributes': {
                    'http.method': 'POST',
                    'http.request.method': 'POST',
                    'http.url': 'https://api.openai.com/v1/completions',
                    'url.full': 'https://api.openai.com/v1/completions',
                    'http.host': 'api.openai.com',
                    'server.address': 'api.openai.com',
                    'network.peer.address': 'api.openai.com',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST api.openai.com/v1/completions',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'logfire.metrics': {
                        'http.client.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.flavor': '1.1',
                                        'http.host': 'api.openai.com',
                                        'http.method': 'POST',
                                        'http.scheme': 'https',
                                        'http.status_code': 200,
                                        'net.peer.name': 'api.openai.com',
                                    },
                                    'total': IsNumeric(),
                                }
                            ],
                            'total': IsNumeric(),
                        },
                        'http.client.request.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.request.method': 'POST',
                                        'http.response.status_code': 200,
                                        'network.protocol.version': '1.1',
                                        'server.address': 'api.openai.com',
                                    },
                                    'total': IsNumeric(),
                                }
                            ],
                            'total': IsNumeric(),
                        },
                    },
                    'http.target': '/v1/completions',
                },
            },
            {
                'name': 'Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'instrumentation_scope': 'logfire.openai',
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_dont_suppress_httpx',
                    'code.lineno': 123,
                    'request_data': {'model': 'gpt-3.5-turbo-instruct', 'prompt': 'xxx'},
                    'gen_ai.provider.name': 'openai',
                    'async': False,
                    'gen_ai.operation.name': 'text_completion',
                    'logfire.msg_template': 'Completion with {request_data[model]!r}',
                    'logfire.msg': "Completion with 'gpt-3.5-turbo-instruct'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.response.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'operation.cost': 5e-06,
                    'response_data': {
                        'finish_reason': 'stop',
                        'text': 'Nine',
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}], 'finish_reason': 'stop'}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.system': {},
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'operation.cost': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    }
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                    'logfire.metrics': {
                        'http.client.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.flavor': '1.1',
                                        'http.host': 'api.openai.com',
                                        'http.method': 'POST',
                                        'http.scheme': 'https',
                                        'http.status_code': 200,
                                        'net.peer.name': 'api.openai.com',
                                    },
                                    'total': IsNumeric,
                                }
                            ],
                            'total': IsNumeric,
                        },
                        'http.client.request.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.request.method': 'POST',
                                        'http.response.status_code': 200,
                                        'network.protocol.version': '1.1',
                                        'server.address': 'api.openai.com',
                                    },
                                    'total': IsNumeric(),
                                }
                            ],
                            'total': IsNumeric(),
                        },
                    },
                },
            },
        ]
    )


def test_suppress_httpx(exporter: TestExporter) -> None:
    with httpx.Client(transport=MockTransport(request_handler)) as httpx_client:
        HTTPXClientInstrumentor().instrument_client(httpx_client)
        # use a hardcoded API key to make sure one in the environment is never used
        openai_client = openai.Client(api_key='foobar', http_client=httpx_client)

        with logfire.instrument_openai(openai_client):
            response = openai_client.completions.create(model='gpt-3.5-turbo-instruct', prompt='xxx')

    assert response.choices[0].text == 'Nine'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True, include_instrumentation_scope=True) == snapshot(
        [
            {
                'name': 'Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'instrumentation_scope': 'logfire.openai',
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_suppress_httpx',
                    'code.lineno': 123,
                    'request_data': {'model': 'gpt-3.5-turbo-instruct', 'prompt': 'xxx'},
                    'gen_ai.provider.name': 'openai',
                    'async': False,
                    'gen_ai.operation.name': 'text_completion',
                    'logfire.msg_template': 'Completion with {request_data[model]!r}',
                    'logfire.msg': "Completion with 'gpt-3.5-turbo-instruct'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.response.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'operation.cost': 5e-06,
                    'response_data': {
                        'finish_reason': 'stop',
                        'text': 'Nine',
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}], 'finish_reason': 'stop'}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.system': {},
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'operation.cost': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    }
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            },
        ]
    )


def test_openai_suppressed(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    with suppress_instrumentation():
        response = instrumented_client.completions.create(model='gpt-3.5-turbo-instruct', prompt='xxx')
    assert response.choices[0].text == 'Nine'
    assert (
        exporter.exported_spans_as_dict(
            parse_json_attributes=True,
        )
        == []
    )


async def test_async_openai_suppressed(instrumented_async_client: openai.AsyncClient, exporter: TestExporter) -> None:
    with suppress_instrumentation():
        response = await instrumented_async_client.completions.create(model='gpt-3.5-turbo-instruct', prompt='xxx')
    assert response.choices[0].text == 'Nine'
    assert (
        exporter.exported_spans_as_dict(
            parse_json_attributes=True,
        )
        == []
    )


def test_create_files(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    response = instrumented_client.files.create(file=BytesIO(b'file contents'), purpose='fine-tune')
    assert response.filename == 'test.txt'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'OpenAI API call to {url!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'request_data': {'purpose': 'fine-tune'},
                    'url': '/files',
                    'async': False,
                    'gen_ai.provider.name': 'openai',
                    'logfire.msg_template': 'OpenAI API call to {url!r}',
                    'logfire.msg': "OpenAI API call to '/files'",
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_create_files',
                    'code.lineno': 123,
                    'gen_ai.system': 'openai',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'url': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.system': {},
                        },
                    },
                },
            }
        ]
    )


async def test_create_files_async(instrumented_async_client: openai.AsyncClient, exporter: TestExporter) -> None:
    response = await instrumented_async_client.files.create(file=BytesIO(b'file contents'), purpose='fine-tune')
    assert response.filename == 'test.txt'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'OpenAI API call to {url!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'request_data': {'purpose': 'fine-tune'},
                    'url': '/files',
                    'async': True,
                    'gen_ai.provider.name': 'openai',
                    'logfire.msg_template': 'OpenAI API call to {url!r}',
                    'logfire.msg': "OpenAI API call to '/files'",
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_create_files_async',
                    'code.lineno': 123,
                    'gen_ai.system': 'openai',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'url': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.system': {},
                        },
                    },
                },
            }
        ]
    )


def test_create_assistant(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    assistant = instrumented_client.beta.assistants.create(
        name='Math Tutor',
        instructions='You are a personal math tutor. Write and run code to answer math questions.',
        tools=[{'type': 'code_interpreter'}],
        model='gpt-4o',
    )
    assert assistant.name == 'Math Tutor'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'OpenAI API call to {url!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'request_data': (
                        {
                            'model': 'gpt-4o',
                            'instructions': 'You are a personal math tutor. Write and run code to answer math questions.',
                            'name': 'Math Tutor',
                            'tools': [{'type': 'code_interpreter'}],
                        }
                    ),
                    'url': '/assistants',
                    'async': False,
                    'gen_ai.provider.name': 'openai',
                    'logfire.msg_template': 'OpenAI API call to {url!r}',
                    'gen_ai.tool.definitions': [{'type': 'code_interpreter'}],
                    'logfire.msg': "OpenAI API call to '/assistants'",
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_create_assistant',
                    'code.lineno': 123,
                    'gen_ai.request.model': 'gpt-4o',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-4-turbo',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'url': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.tool.definitions': {},
                            'gen_ai.request.model': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                        },
                    },
                },
            }
        ]
    )


def test_create_thread(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    with pytest.warns(DeprecationWarning):
        thread = instrumented_client.beta.threads.create()  # type: ignore
    assert thread.id == 'thread_abc123'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'OpenAI API call to {url!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'request_data': {},
                    'url': '/threads',
                    'async': False,
                    'gen_ai.provider.name': 'openai',
                    'logfire.msg_template': 'OpenAI API call to {url!r}',
                    'logfire.msg': "OpenAI API call to '/threads'",
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_create_thread',
                    'code.lineno': 123,
                    'gen_ai.system': 'openai',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'url': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.system': {},
                        },
                    },
                },
            }
        ]
    )


@pytest.mark.vcr()
def test_responses_api(exporter: TestExporter) -> None:
    client = openai.Client()
    logfire.instrument_openai(client)
    tools: Any = [
        {
            'type': 'function',
            'name': 'get_weather',
            'description': 'Get current temperature for a given location.',
            'parameters': {
                'type': 'object',
                'properties': {'location': {'type': 'string', 'description': 'City and country e.g. Bogotá, Colombia'}},
                'required': ['location'],
                'additionalProperties': False,
            },
        }
    ]

    input_messages: Any = [{'role': 'user', 'content': 'What is the weather like in Paris today?'}]
    response = client.responses.create(
        model='gpt-4.1', input=input_messages[0]['content'], tools=tools, instructions='Be nice'
    )
    tool_call: Any = response.output[0]
    input_messages.append(tool_call)
    input_messages.append({'type': 'function_call_output', 'call_id': tool_call.call_id, 'output': 'Rainy'})
    response2: Any = client.responses.create(model='gpt-4.1', input=input_messages)
    assert response2.output[0].content[0].text == snapshot(
        "The weather in Paris today is rainy. If you're planning to go out, don't forget an umbrella!"
    )
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_responses_api',
                    'code.lineno': 123,
                    'gen_ai.provider.name': 'openai',
                    'async': False,
                    'request_data': {'model': 'gpt-4.1', 'stream': False},
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.tool.definitions': [
                        {
                            'type': 'function',
                            'name': 'get_weather',
                            'description': 'Get current temperature for a given location.',
                            'parameters': {
                                'type': 'object',
                                'properties': {
                                    'location': {
                                        'type': 'string',
                                        'description': 'City and country e.g. Bogotá, Colombia',
                                    }
                                },
                                'required': ['location'],
                                'additionalProperties': False,
                            },
                        }
                    ],
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.msg': "Responses API with 'gpt-4.1'",
                    'gen_ai.system': 'openai',
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.request.model': 'gpt-4.1',
                    'gen_ai.response.model': 'gpt-4.1-2025-04-14',
                    'events': [
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'role': 'assistant',
                            'tool_calls': [
                                {
                                    'id': 'call_uilZSE2qAuMA2NWct72DBwd6',
                                    'type': 'function',
                                    'function': {'name': 'get_weather', 'arguments': '{"location":"Paris, France"}'},
                                }
                            ],
                        }
                    ],
                    'gen_ai.usage.input_tokens': 65,
                    'gen_ai.usage.output_tokens': 17,
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'tool_call',
                                    'id': 'call_uilZSE2qAuMA2NWct72DBwd6',
                                    'name': 'get_weather',
                                    'arguments': '{"location":"Paris, France"}',
                                }
                            ],
                        }
                    ],
                    'operation.cost': 0.000266,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.provider.name': {},
                            'events': {'type': 'array'},
                            'gen_ai.request.model': {},
                            'request_data': {'type': 'object'},
                            'gen_ai.operation.name': {},
                            'gen_ai.tool.definitions': {},
                            'gen_ai.system': {},
                            'async': {},
                            'gen_ai.response.model': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'operation.cost': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            },
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_responses_api',
                    'code.lineno': 123,
                    'gen_ai.provider.name': 'openai',
                    'async': False,
                    'request_data': {'model': 'gpt-4.1', 'stream': False},
                    'gen_ai.operation.name': 'chat',
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.msg': "Responses API with 'gpt-4.1'",
                    'logfire.tags': ('LLM',),
                    'gen_ai.system': 'openai',
                    'logfire.span_type': 'span',
                    'gen_ai.request.model': 'gpt-4.1',
                    'gen_ai.response.model': 'gpt-4.1-2025-04-14',
                    'gen_ai.usage.input_tokens': 43,
                    'events': [
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'content': "The weather in Paris today is rainy. If you're planning to go out, don't forget an umbrella!",
                            'role': 'assistant',
                        }
                    ],
                    'gen_ai.usage.output_tokens': 21,
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'text',
                                    'content': "The weather in Paris today is rainy. If you're planning to go out, don't forget an umbrella!",
                                }
                            ],
                        }
                    ],
                    'operation.cost': 0.000254,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.provider.name': {},
                            'events': {'type': 'array'},
                            'gen_ai.request.model': {},
                            'request_data': {'type': 'object'},
                            'gen_ai.operation.name': {},
                            'gen_ai.system': {},
                            'async': {},
                            'gen_ai.response.model': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'operation.cost': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            },
        ]
    )


@pytest.mark.vcr()
def test_responses_api_nonrecording(exporter: TestExporter, config_kwargs: dict[str, Any]) -> None:
    client = openai.Client()
    logfire.instrument_openai(client)
    logfire.configure(**config_kwargs, sampling=logfire.SamplingOptions(head=0))
    with logfire.span('span'):
        response = client.responses.create(model='gpt-4.1', input='hi')
    assert response.output_text == snapshot('Hello! How can I help you today? 😊')

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == []


@pytest.mark.vcr()
def test_openrouter_streaming_reasoning(exporter: TestExporter) -> None:
    client = openai.Client(base_url='https://openrouter.ai/api/v1')
    logfire.instrument_openai(client)

    response = client.chat.completions.create(
        model='google/gemini-2.5-flash',
        messages=[{'role': 'user', 'content': 'Hello, how are you? (This is a trick question)'}],
        stream=True,
        extra_body={'reasoning': {'effort': 'low'}},
    )

    for _ in response:
        ...

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_openrouter_streaming_reasoning',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'user', 'content': 'Hello, how are you? (This is a trick question)'}],
                        'model': 'google/gemini-2.5-flash',
                        'stream': True,
                    },
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'google/gemini-2.5-flash',
                    'gen_ai.operation.name': 'chat',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'google/gemini-2.5-flash'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.response.model': 'google/gemini-2.5-flash',
                },
            },
            {
                'name': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'logfire.msg': "streaming response from 'google/gemini-2.5-flash' took 1.00s",
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_openrouter_streaming_reasoning',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'user', 'content': 'Hello, how are you? (This is a trick question)'}],
                        'model': 'google/gemini-2.5-flash',
                        'stream': True,
                    },
                    'gen_ai.request.model': 'google/gemini-2.5-flash',
                    'gen_ai.provider.name': 'openai',
                    'async': False,
                    'gen_ai.operation.name': 'chat',
                    'duration': 1.0,
                    'response_data': {
                        'message': {
                            'content': """\
That's a clever way to put it! You're right, it is a bit of a trick question for an AI.

As a large language model, I don't experience emotions, have a physical body, or "feel" things in the human sense, so I can't really quantify "how" I am.

However, I am fully operational, my systems are running smoothly, and I'm ready to assist you!

So, while I can't genuinely answer it for myself, how are *you* doing today, and what can I help you with?\
""",
                            'refusal': None,
                            'role': 'assistant',
                            'annotations': None,
                            'audio': None,
                            'function_call': None,
                            'tool_calls': None,
                            'parsed': None,
                            'reasoning': """\
**Interpreting User Intent**

I'm zeroing in on the core of the query. The "how are you" is basic, but the "trick question" label is key. My focus is on decoding what the user *really* wants. I'm anticipating something beyond a simple pleasantry.


""",
                            'reasoning_details': [
                                {
                                    'type': 'reasoning.text',
                                    'text': """\
**Interpreting User Intent**

I'm zeroing in on the core of the query. The "how are you" is basic, but the "trick question" label is key. My focus is on decoding what the user *really* wants. I'm anticipating something beyond a simple pleasantry.


""",
                                    'provider': 'google-vertex',
                                }
                            ],
                        },
                        'usage': {
                            'completion_tokens': 1003,
                            'prompt_tokens': 13,
                            'total_tokens': 1016,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'async': {},
                            'gen_ai.operation.name': {},
                            'duration': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ParsedChatCompletionMessage[object]',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'google/gemini-2.5-flash',
                },
            },
        ]
    )


def test_sync_chat_completions_empty_messages(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    """Test OpenAI chat completions with empty messages."""
    response = instrumented_client.chat.completions.create(
        model='gpt-4',
        messages=[],
    )
    assert response.choices[0].message.content == 'Nine'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_sync_chat_completions_empty_messages',
                    'code.lineno': 123,
                    'request_data': {'messages': [], 'model': 'gpt-4'},
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-4',
                    'operation.cost': 0.00012,
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'response_data': {
                        'message': {
                            'content': 'Nine',
                            'refusal': None,
                            'role': 'assistant',
                            'annotations': None,
                            'audio': None,
                            'function_call': None,
                            'tool_calls': None,
                        },
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}], 'finish_reason': 'stop'}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'operation.cost': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ChatCompletionMessage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


def test_responses_api_empty_inputs(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    """Test OpenAI responses API with empty inputs."""
    response = instrumented_client.responses.create(
        model='gpt-4.1',
        input=None,  # type: ignore
        instructions='You are a helpful assistant.',
    )
    assert response.output[0].content[0].text == 'Nine'  # type: ignore
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_responses_api_empty_inputs',
                    'code.lineno': 123,
                    'gen_ai.request.model': 'gpt-4.1',
                    'request_data': {'model': 'gpt-4.1', 'stream': False},
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'async': False,
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.msg': "Responses API with 'gpt-4.1'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-4.1',
                    'operation.cost': 2.8e-05,
                    'gen_ai.usage.input_tokens': 10,
                    'gen_ai.usage.output_tokens': 1,
                    'gen_ai.output.messages': [{'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}]}],
                    'events': [{'event.name': 'gen_ai.assistant.message', 'content': 'Nine', 'role': 'assistant'}],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.request.model': {},
                            'request_data': {'type': 'object'},
                            'events': {'type': 'array'},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'operation.cost': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


def test_chat_completions_no_finish_reason(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    """Test OpenAI chat completions with None finish_reason."""
    response = instrumented_client.chat.completions.create(
        model='gpt-4',
        messages=[{'role': 'user', 'content': 'test no finish reason'}],
    )
    assert response.choices[0].message.content == 'Nine'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_chat_completions_no_finish_reason',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'user', 'content': 'test no finish reason'}],
                        'model': 'gpt-4',
                    },
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-4',
                    'operation.cost': 0.00012,
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'response_data': {
                        'message': {
                            'content': 'Nine',
                            'refusal': None,
                            'role': 'assistant',
                            'annotations': None,
                            'audio': None,
                            'function_call': None,
                            'tool_calls': None,
                        },
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'gen_ai.output.messages': [{'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}]}],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'operation.cost': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ChatCompletionMessage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


def test_completions_no_finish_reason(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    """Test OpenAI completions with None finish_reason."""
    response = instrumented_client.completions.create(
        model='gpt-3.5-turbo-instruct',
        prompt='test no finish reason',
    )
    assert response.choices[0].text == 'Nine'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_completions_no_finish_reason',
                    'code.lineno': 123,
                    'request_data': {'model': 'gpt-3.5-turbo-instruct', 'prompt': 'test no finish reason'},
                    'gen_ai.request.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.operation.name': 'text_completion',
                    'async': False,
                    'logfire.msg_template': 'Completion with {request_data[model]!r}',
                    'logfire.msg': "Completion with 'gpt-3.5-turbo-instruct'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-3.5-turbo-instruct',
                    'operation.cost': 5e-06,
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'response_data': {
                        'finish_reason': None,
                        'text': 'Nine',
                        'usage': {
                            'completion_tokens': 1,
                            'prompt_tokens': 2,
                            'total_tokens': 3,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}], 'finish_reason': None}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'operation.cost': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    }
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


def test_chat_completions_tool_call_response(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    """Test output message conversion when response has tool_calls but no content."""
    response = instrumented_client.chat.completions.create(
        model='gpt-4',
        messages=[{'role': 'user', 'content': 'call a function for me'}],
    )
    assert response.choices[0].message.tool_calls is not None
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_chat_completions_tool_call_response',
                    'code.lineno': 123,
                    'request_data': {
                        'messages': [{'role': 'user', 'content': 'call a function for me'}],
                        'model': 'gpt-4',
                    },
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-4',
                    'operation.cost': 0.00165,
                    'gen_ai.usage.input_tokens': 25,
                    'gen_ai.usage.output_tokens': 15,
                    'response_data': {
                        'message': {
                            'content': None,
                            'refusal': None,
                            'role': 'assistant',
                            'annotations': None,
                            'audio': None,
                            'function_call': None,
                            'tool_calls': [
                                {
                                    'id': 'call_xyz789',
                                    'function': {'arguments': '{"location": "San Francisco"}', 'name': 'get_weather'},
                                    'type': 'function',
                                }
                            ],
                        },
                        'usage': {
                            'completion_tokens': 15,
                            'prompt_tokens': 25,
                            'total_tokens': 40,
                            'completion_tokens_details': None,
                            'prompt_tokens_details': None,
                        },
                    },
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'tool_call',
                                    'id': 'call_xyz789',
                                    'name': 'get_weather',
                                    'arguments': {'location': 'San Francisco'},
                                }
                            ],
                            'finish_reason': 'tool_calls',
                        }
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'operation.cost': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'message': {
                                        'type': 'object',
                                        'title': 'ChatCompletionMessage',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'tool_calls': {
                                                'type': 'array',
                                                'items': {
                                                    'type': 'object',
                                                    'title': 'ChatCompletionMessageFunctionToolCall',
                                                    'x-python-datatype': 'PydanticModel',
                                                    'properties': {
                                                        'function': {
                                                            'type': 'object',
                                                            'title': 'Function',
                                                            'x-python-datatype': 'PydanticModel',
                                                        }
                                                    },
                                                },
                                            }
                                        },
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'CompletionUsage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )
