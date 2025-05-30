from __future__ import annotations as _annotations

import json
import sys
from io import BytesIO
from typing import Any, AsyncIterator, Iterator

import httpx
import openai
import pytest
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
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

import logfire
from logfire._internal.utils import suppress_instrumentation
from logfire.testing import TestExporter

pytestmark = pytest.mark.skipif(sys.version_info < (3, 9), reason='Newest OpenAI SDK does not support 3.8')


def request_handler(request: httpx.Request) -> httpx.Response:
    """Used to mock httpx requests

    We do this instead of using pytest-httpx since 1) it's nearly as simple 2) pytest-httpx doesn't support Python 3.8.
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
            chunks = [
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
            return httpx.Response(200, text=''.join(f'data: {chunk.model_dump_json()}\n\n' for chunk in chunks))
        else:
            return httpx.Response(
                200,
                json=completion.Completion(
                    id='test_id',
                    choices=[completion_choice.CompletionChoice(finish_reason='stop', index=0, text='Nine')],
                    created=123,
                    model='gpt-3.5-turbo-instruct',
                    object='text_completion',
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
                    'request_data': (
                        {
                            'messages': [
                                {'role': 'system', 'content': 'You are a helpful assistant.'},
                                {'role': 'user', 'content': 'What is four plus five?'},
                            ],
                            'model': 'gpt-4',
                        }
                    ),
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.response.model': 'gpt-4',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'response_data': (
                        {
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
                        }
                    ),
                    'logfire.json_schema': (
                        {
                            'type': 'object',
                            'properties': {
                                'request_data': {'type': 'object'},
                                'async': {},
                                'gen_ai.system': {},
                                'gen_ai.request.model': {},
                                'gen_ai.response.model': {},
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
                            },
                        }
                    ),
                },
            }
        ]
    )


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
                    'request_data': (
                        {
                            'messages': [
                                {'role': 'system', 'content': 'You are a helpful assistant.'},
                                {'role': 'user', 'content': 'What is four plus five?'},
                            ],
                            'model': 'gpt-4',
                        }
                    ),
                    'async': True,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.response.model': 'gpt-4',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 1,
                    'response_data': (
                        {
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
                        }
                    ),
                    'logfire.json_schema': (
                        {
                            'type': 'object',
                            'properties': {
                                'request_data': {'type': 'object'},
                                'async': {},
                                'gen_ai.system': {},
                                'gen_ai.request.model': {},
                                'gen_ai.response.model': {},
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
                            },
                        }
                    ),
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
                    'gen_ai.request.model': 'gpt-4',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'gen_ai.request.model': {}, 'async': {}},
                    },
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
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
                    'logfire.span_type': 'log',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': {'combined_chunk_content': '', 'chunk_count': 0},
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'async': {},
                            'duration': {},
                            'response_data': {'type': 'object'},
                        },
                    },
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
                    'gen_ai.request.model': 'gpt-4',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'gen_ai.request.model': {}, 'async': {}},
                    },
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
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
                    'logfire.span_type': 'log',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': {'message': None, 'usage': None},
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'async': {},
                            'duration': {},
                            'response_data': {'type': 'object'},
                        },
                    },
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
                    'gen_ai.request.model': 'gpt-4',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'gen_ai.request.model': {}, 'async': {}},
                    },
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
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
                    'async': False,
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
                            'async': {},
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
                    'gen_ai.request.model': 'gpt-4',
                    'async': True,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'gen_ai.request.model': {}, 'async': {}},
                    },
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
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
                    'async': True,
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
                            'async': {},
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
                    'gen_ai.request.model': 'gpt-4',
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'gen_ai.request.model': {}, 'async': {}},
                    },
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
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
                    'logfire.span_type': 'log',
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
                            'async': {},
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
                    'gen_ai.request.model': 'gpt-4',
                    'async': True,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'gen_ai.request.model': {}, 'async': {}},
                    },
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
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
                    'logfire.span_type': 'log',
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
                            'async': {},
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
                    'async': False,
                    'logfire.msg_template': 'Completion with {request_data[model]!r}',
                    'logfire.msg': "Completion with 'gpt-3.5-turbo-instruct'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.response.model': 'gpt-3.5-turbo-instruct',
                    'response_data': {'finish_reason': 'stop', 'text': 'Nine', 'usage': None},
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
                            'response_data': {'type': 'object'},
                        },
                    },
                },
            }
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
                    'gen_ai.request.model': 'gpt-3.5-turbo-instruct',
                    'async': False,
                    'logfire.msg_template': 'Completion with {request_data[model]!r}',
                    'logfire.msg': "Completion with 'gpt-3.5-turbo-instruct'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'gen_ai.request.model': {}, 'async': {}},
                    },
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
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
                    'logfire.span_type': 'log',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': {'combined_chunk_content': 'The answer is Nine', 'chunk_count': 2},
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.request.model': {},
                            'async': {},
                            'duration': {},
                            'response_data': {'type': 'object'},
                        },
                    },
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
                    'async': False,
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
                            'async': {},
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
                    'gen_ai.request.model': 'dall-e-3',
                    'async': False,
                    'logfire.msg_template': 'Image Generation with {request_data[model]!r}',
                    'logfire.msg': "Image Generation with 'dall-e-3'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.system': 'openai',
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
                            'gen_ai.request.model': {},
                            'async': {},
                            'gen_ai.system': {},
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
                    'async': False,
                    'logfire.msg_template': 'Completion with {request_data[model]!r}',
                    'logfire.msg': "Completion with 'gpt-3.5-turbo-instruct'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.response.model': 'gpt-3.5-turbo-instruct',
                    'response_data': {'finish_reason': 'stop', 'text': 'Nine', 'usage': None},
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
                            'response_data': {'type': 'object'},
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
                    'async': False,
                    'logfire.msg_template': 'Completion with {request_data[model]!r}',
                    'logfire.msg': "Completion with 'gpt-3.5-turbo-instruct'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-3.5-turbo-instruct',
                    'gen_ai.response.model': 'gpt-3.5-turbo-instruct',
                    'response_data': {'finish_reason': 'stop', 'text': 'Nine', 'usage': None},
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
                            'response_data': {'type': 'object'},
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
                    'logfire.msg_template': 'OpenAI API call to {url!r}',
                    'logfire.msg': "OpenAI API call to '/files'",
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_create_files',
                    'code.lineno': 123,
                    'gen_ai.system': 'openai',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'url': {}, 'async': {}, 'gen_ai.system': {}},
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
                    'logfire.msg_template': 'OpenAI API call to {url!r}',
                    'logfire.msg': "OpenAI API call to '/files'",
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_create_files_async',
                    'code.lineno': 123,
                    'gen_ai.system': 'openai',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'url': {}, 'async': {}, 'gen_ai.system': {}},
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
                    'logfire.msg_template': 'OpenAI API call to {url!r}',
                    'logfire.msg': "OpenAI API call to '/assistants'",
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_create_assistant',
                    'code.lineno': 123,
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-4o',
                    'gen_ai.response.model': 'gpt-4-turbo',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'url': {},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
                        },
                    },
                },
            }
        ]
    )


def test_create_thread(instrumented_client: openai.Client, exporter: TestExporter) -> None:
    thread = instrumented_client.beta.threads.create()
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
                    'logfire.msg_template': 'OpenAI API call to {url!r}',
                    'logfire.msg': "OpenAI API call to '/threads'",
                    'code.filepath': 'test_openai.py',
                    'code.function': 'test_create_thread',
                    'code.lineno': 123,
                    'gen_ai.system': 'openai',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'url': {}, 'async': {}, 'gen_ai.system': {}},
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
        'The weather in Paris today is rainy. If you’re planning to go out, '
        'don’t forget your umbrella! Let me know if you need more details or the forecast for the next few days.'
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
                    'async': False,
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.msg': "Responses API with 'gpt-4.1'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-4.1',
                    'gen_ai.response.model': 'gpt-4.1-2025-04-14',
                    'gen_ai.usage.input_tokens': 65,
                    'gen_ai.usage.output_tokens': 17,
                    'events': [
                        {'event.name': 'gen_ai.system.message', 'content': 'Be nice', 'role': 'system'},
                        {
                            'event.name': 'gen_ai.user.message',
                            'content': 'What is the weather like in Paris today?',
                            'role': 'user',
                        },
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'role': 'assistant',
                            'tool_calls': [
                                {
                                    'id': 'call_92k1J8QkHaqVZFGoZU1aLvR7',
                                    'type': 'function',
                                    'function': {'name': 'get_weather', 'arguments': '{"location":"Paris, France"}'},
                                }
                            ],
                        },
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.request.model': {},
                            'events': {'type': 'array'},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
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
                    'async': False,
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.msg': "Responses API with 'gpt-4.1'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-4.1',
                    'gen_ai.response.model': 'gpt-4.1-2025-04-14',
                    'gen_ai.usage.input_tokens': 43,
                    'gen_ai.usage.output_tokens': 40,
                    'events': [
                        {
                            'event.name': 'gen_ai.user.message',
                            'content': 'What is the weather like in Paris today?',
                            'role': 'user',
                        },
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'role': 'assistant',
                            'tool_calls': [
                                {
                                    'id': 'call_92k1J8QkHaqVZFGoZU1aLvR7',
                                    'type': 'function',
                                    'function': {'name': 'get_weather', 'arguments': '{"location":"Paris, France"}'},
                                }
                            ],
                        },
                        {
                            'event.name': 'gen_ai.tool.message',
                            'role': 'tool',
                            'id': 'call_92k1J8QkHaqVZFGoZU1aLvR7',
                            'content': 'Rainy',
                            'name': 'get_weather',
                        },
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'content': 'The weather in Paris today is rainy. If you’re planning to go out, don’t forget your umbrella! Let me know if you need more details or the forecast for the next few days.',
                            'role': 'assistant',
                        },
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.request.model': {},
                            'events': {'type': 'array'},
                            'async': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
        ]
    )
