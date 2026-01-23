from __future__ import annotations as _annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any, cast

import anthropic
import httpx
import pydantic
import pytest
from anthropic.types import (
    Completion,
    Message,
    MessageDeltaUsage,
    MessageStartEvent,
    MessageStopEvent,
    TextBlock,
    TextDelta,
    Usage,
)
from dirty_equals import IsJson, IsPartialDict, IsStr
from httpx._transports.mock import MockTransport
from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter

ANY_ADAPTER = pydantic.TypeAdapter(Any)  # type: ignore


def request_handler(request: httpx.Request) -> httpx.Response:
    """Used to mock httpx requests

    We do this instead of using pytest-httpx since 1) it's nearly as simple 2) pytest-httpx doesn't support Python 3.8.
    (We no longer support 3.8 either, but it's not worth changing this now)
    """
    assert request.method == 'POST'
    if request.url == 'https://api.anthropic.com/v1/complete':
        return httpx.Response(
            200,
            json=Completion(id='test_id', completion='completion', model='claude-2.1', type='completion').model_dump(
                mode='json'
            ),
        )
    assert request.url in ['https://api.anthropic.com/v1/messages'], f'Unexpected URL: {request.url}'
    json_body = json.loads(request.content)
    if json_body.get('stream'):
        if json_body['system'] == 'empty response chunk':
            return httpx.Response(200, text='data: []\n\n')
        else:
            chunks = [
                MessageStartEvent(
                    message=Message(
                        id='test_id',
                        content=[],
                        model='claude-3-haiku-20240307',
                        role='assistant',
                        stop_reason=None,
                        stop_sequence=None,
                        type='message',
                        usage=Usage(input_tokens=25, output_tokens=25),
                    ),
                    type='message_start',
                ),
                dict(content_block=TextBlock(text='', type='text'), index=0, type='content_block_start'),
                dict(delta=TextDelta(text='The answer', type='text_delta'), index=0, type='content_block_delta'),
                dict(delta=TextDelta(text=' is secret', type='text_delta'), index=0, type='content_block_delta'),
                dict(index=0, type='content_block_stop'),
                dict(
                    delta=dict(stop_reason='end_turn', stop_sequence=None),
                    type='message_delta',
                    usage=MessageDeltaUsage(output_tokens=55),
                ),
                MessageStopEvent(type='message_stop'),
            ]
            chunks_dicts = ANY_ADAPTER.dump_python(chunks)  # type: ignore
            return httpx.Response(
                200, text=''.join(f'event: {chunk["type"]}\ndata: {json.dumps(chunk)}\n\n' for chunk in chunks_dicts)
            )
    elif json_body['system'] == 'tool response':
        return httpx.Response(
            200,
            json=Message.model_construct(
                id='test_id',
                content=[dict(id='id', input={'param': 'param'}, name='tool', type='tool_use')],
                model='claude-3-haiku-20240307',
                role='assistant',
                type='message',
                usage=Usage(input_tokens=2, output_tokens=3),
            ).model_dump(mode='json'),
        )
    elif json_body['system'] == 'image content':
        return httpx.Response(
            200,
            json=Message(
                id='test_image_id',
                content=[
                    TextBlock(
                        text='I can see a cat in the image.',
                        type='text',
                    )
                ],
                model='claude-3-haiku-20240307',
                role='assistant',
                type='message',
                usage=Usage(input_tokens=100, output_tokens=8),
            ).model_dump(mode='json'),
        )
    elif json_body['system'] == 'tool use conversation':
        return httpx.Response(
            200,
            json=Message(
                id='test_tool_conv_id',
                content=[
                    TextBlock(
                        text='The weather in Boston is sunny and 72°F.',
                        type='text',
                    )
                ],
                model='claude-3-haiku-20240307',
                role='assistant',
                type='message',
                usage=Usage(input_tokens=50, output_tokens=15),
            ).model_dump(mode='json'),
        )
    else:
        return httpx.Response(
            200,
            json=Message(
                id='test_id',
                content=[
                    TextBlock(
                        text='Nine',
                        type='text',
                    )
                ],
                model='claude-3-haiku-20240307',
                role='assistant',
                type='message',
                usage=Usage(input_tokens=2, output_tokens=3),
            ).model_dump(mode='json'),
        )


@pytest.fixture
def instrumented_client() -> Iterator[anthropic.Anthropic]:
    with httpx.Client(transport=MockTransport(request_handler)) as httpx_client:
        # use a hardcoded API key to make sure one in the environment is never used
        anthropic_client = anthropic.Anthropic(api_key='foobar', http_client=httpx_client)

        with logfire.instrument_anthropic(anthropic_client):
            yield anthropic_client


@pytest.fixture
async def instrumented_async_client() -> AsyncIterator[anthropic.AsyncAnthropic]:
    async with httpx.AsyncClient(transport=MockTransport(request_handler)) as httpx_client:
        # use a hardcoded API key to make sure one in the environment is never used
        anthropic_client = anthropic.AsyncAnthropic(api_key='foobar', http_client=httpx_client)

        # Test instrumenting EVERYTHING
        with logfire.instrument_anthropic():
            yield anthropic_client


def test_sync_messages(instrumented_client: anthropic.Anthropic, exporter: TestExporter) -> None:
    response = instrumented_client.messages.create(
        max_tokens=1000,
        model='claude-3-haiku-20240307',
        system='You are a helpful assistant.',
        messages=[{'role': 'user', 'content': 'What is four plus five?'}],
    )
    assert isinstance(response.content[0], TextBlock)
    assert response.content[0].text == 'Nine'
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Message with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_sync_messages',
                    'code.lineno': 123,
                    'request_data': IsJson(
                        snapshot(
                            {
                                'max_tokens': 1000,
                                'system': 'You are a helpful assistant.',
                                'messages': [{'role': 'user', 'content': 'What is four plus five?'}],
                                'model': 'claude-3-haiku-20240307',
                            }
                        )
                    ),
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': IsJson(
                        [{'role': 'user', 'parts': [{'type': 'text', 'content': 'What is four plus five?'}]}]
                    ),
                    'gen_ai.system_instructions': IsJson([{'type': 'text', 'content': 'You are a helpful assistant.'}]),
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'response_data': IsJson(
                        snapshot(
                            {
                                'message': {
                                    'content': 'Nine',
                                    'role': 'assistant',
                                },
                                'usage': IsPartialDict(
                                    {
                                        'cache_creation': None,
                                        'input_tokens': 2,
                                        'output_tokens': 3,
                                        'cache_creation_input_tokens': None,
                                        'cache_read_input_tokens': None,
                                        'server_tool_use': None,
                                        'service_tier': None,
                                    }
                                ),
                            }
                        )
                    ),
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
                    'gen_ai.response.id': 'test_id',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 3,
                    'gen_ai.output.messages': IsJson(
                        [{'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}]}]
                    ),
                    'logfire.json_schema': IsJson(
                        snapshot(
                            {
                                'type': 'object',
                                'properties': {
                                    'request_data': {'type': 'object'},
                                    'gen_ai.provider.name': {},
                                    'gen_ai.operation.name': {},
                                    'gen_ai.request.model': {},
                                    'gen_ai.request.max_tokens': {},
                                    'gen_ai.input.messages': {'type': 'array'},
                                    'gen_ai.system_instructions': {'type': 'array'},
                                    'async': {},
                                    'response_data': {
                                        'type': 'object',
                                        'properties': {
                                            'usage': {
                                                'type': 'object',
                                                'title': 'Usage',
                                                'x-python-datatype': 'PydanticModel',
                                            },
                                        },
                                    },
                                    'gen_ai.response.model': {},
                                    'gen_ai.response.id': {},
                                    'gen_ai.usage.input_tokens': {},
                                    'gen_ai.usage.output_tokens': {},
                                    'gen_ai.output.messages': {'type': 'array'},
                                },
                            }
                        )
                    ),
                },
            }
        ]
    )


async def test_async_messages(instrumented_async_client: anthropic.AsyncAnthropic, exporter: TestExporter) -> None:
    response = await instrumented_async_client.messages.create(
        max_tokens=1000,
        model='claude-3-haiku-20240307',
        system='You are a helpful assistant.',
        messages=[{'role': 'user', 'content': 'What is four plus five?'}],
    )
    assert isinstance(response.content[0], TextBlock)
    assert response.content[0].text == 'Nine'
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Message with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_async_messages',
                    'code.lineno': 123,
                    'request_data': IsJson(
                        {
                            'max_tokens': 1000,
                            'system': 'You are a helpful assistant.',
                            'messages': [{'role': 'user', 'content': 'What is four plus five?'}],
                            'model': 'claude-3-haiku-20240307',
                        }
                    ),
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': IsJson(
                        [{'role': 'user', 'parts': [{'type': 'text', 'content': 'What is four plus five?'}]}]
                    ),
                    'gen_ai.system_instructions': IsJson([{'type': 'text', 'content': 'You are a helpful assistant.'}]),
                    'async': True,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'response_data': IsJson(
                        snapshot(
                            {
                                'message': {
                                    'content': 'Nine',
                                    'role': 'assistant',
                                },
                                'usage': IsPartialDict(
                                    {
                                        'cache_creation': None,
                                        'input_tokens': 2,
                                        'output_tokens': 3,
                                        'cache_creation_input_tokens': None,
                                        'cache_read_input_tokens': None,
                                        'server_tool_use': None,
                                        'service_tier': None,
                                    }
                                ),
                            }
                        )
                    ),
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
                    'gen_ai.response.id': 'test_id',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 3,
                    'gen_ai.output.messages': IsJson(
                        [{'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Nine'}]}]
                    ),
                    'logfire.json_schema': IsJson(
                        {
                            'type': 'object',
                            'properties': {
                                'request_data': {'type': 'object'},
                                'gen_ai.provider.name': {},
                                'gen_ai.operation.name': {},
                                'gen_ai.request.model': {},
                                'gen_ai.request.max_tokens': {},
                                'gen_ai.input.messages': {'type': 'array'},
                                'gen_ai.system_instructions': {'type': 'array'},
                                'async': {},
                                'response_data': {
                                    'type': 'object',
                                    'properties': {
                                        'usage': {
                                            'type': 'object',
                                            'title': 'Usage',
                                            'x-python-datatype': 'PydanticModel',
                                        },
                                    },
                                },
                                'gen_ai.response.model': {},
                                'gen_ai.response.id': {},
                                'gen_ai.usage.input_tokens': {},
                                'gen_ai.usage.output_tokens': {},
                                'gen_ai.output.messages': {'type': 'array'},
                            },
                        },
                    ),
                },
            }
        ]
    )


def test_sync_message_empty_response_chunk(instrumented_client: anthropic.Anthropic, exporter: TestExporter) -> None:
    response = instrumented_client.messages.create(
        max_tokens=1000,
        model='claude-3-haiku-20240307',
        system='empty response chunk',
        messages=[],
        stream=True,
    )
    combined = [chunk for chunk in response]
    assert combined == []
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Message with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_sync_message_empty_response_chunk',
                    'code.lineno': 123,
                    'request_data': '{"max_tokens":1000,"messages":[],"model":"claude-3-haiku-20240307","stream":true,"system":"empty response chunk"}',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': IsJson([]),
                    'gen_ai.system_instructions': IsJson([{'type': 'text', 'content': 'empty response chunk'}]),
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.request.max_tokens":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
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
                    'request_data': '{"max_tokens":1000,"messages":[],"model":"claude-3-haiku-20240307","stream":true,"system":"empty response chunk"}',
                    'async': False,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_sync_message_empty_response_chunk',
                    'code.lineno': 123,
                    'logfire.msg': "streaming response from 'claude-3-haiku-20240307' took 1.00s",
                    'logfire.span_type': 'log',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': IsJson([]),
                    'gen_ai.system_instructions': IsJson([{'type': 'text', 'content': 'empty response chunk'}]),
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': '{"combined_chunk_content":"","chunk_count":0}',
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.request.max_tokens":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{},"response_data":{"type":"object"}}}',
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
                },
            },
        ]
    )


def test_sync_messages_stream(instrumented_client: anthropic.Anthropic, exporter: TestExporter) -> None:
    response = instrumented_client.messages.create(
        max_tokens=1000,
        model='claude-3-haiku-20240307',
        system='You are a helpful assistant.',
        messages=[{'role': 'user', 'content': 'What is four plus five?'}],
        stream=True,
    )
    with response as stream:
        combined = ''.join(
            chunk.delta.text  # type: ignore
            for chunk in stream
            if hasattr(chunk, 'delta') and isinstance(chunk.delta, TextDelta)  # type: ignore
        )
    assert combined == 'The answer is secret'
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Message with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_sync_messages_stream',
                    'code.lineno': 123,
                    'request_data': '{"max_tokens":1000,"messages":[{"role":"user","content":"What is four plus five?"}],"model":"claude-3-haiku-20240307","stream":true,"system":"You are a helpful assistant."}',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': IsJson(
                        [{'role': 'user', 'parts': [{'type': 'text', 'content': 'What is four plus five?'}]}]
                    ),
                    'gen_ai.system_instructions': IsJson([{'type': 'text', 'content': 'You are a helpful assistant.'}]),
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.request.max_tokens":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
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
                    'request_data': '{"max_tokens":1000,"messages":[{"role":"user","content":"What is four plus five?"}],"model":"claude-3-haiku-20240307","stream":true,"system":"You are a helpful assistant."}',
                    'async': False,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'code.filepath': 'test_anthropic.py',
                    'code.function': '<genexpr>',
                    'code.lineno': 123,
                    'logfire.msg': "streaming response from 'claude-3-haiku-20240307' took 1.00s",
                    'logfire.span_type': 'log',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': IsJson(
                        [{'role': 'user', 'parts': [{'type': 'text', 'content': 'What is four plus five?'}]}]
                    ),
                    'gen_ai.system_instructions': IsJson([{'type': 'text', 'content': 'You are a helpful assistant.'}]),
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': '{"combined_chunk_content":"The answer is secret","chunk_count":2}',
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.request.max_tokens":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{},"response_data":{"type":"object"}}}',
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
                },
            },
        ]
    )


async def test_async_messages_stream(
    instrumented_async_client: anthropic.AsyncAnthropic, exporter: TestExporter
) -> None:
    response = await instrumented_async_client.messages.create(
        max_tokens=1000,
        model='claude-3-haiku-20240307',
        system='You are a helpful assistant.',
        messages=[{'role': 'user', 'content': 'What is four plus five?'}],
        stream=True,
    )
    async with response as stream:
        chunk_content = [
            chunk.delta.text  # type: ignore
            async for chunk in stream
            if hasattr(chunk, 'delta') and isinstance(chunk.delta, TextDelta)  # type: ignore
        ]
        combined = ''.join(chunk_content)
    assert combined == 'The answer is secret'
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Message with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_async_messages_stream',
                    'code.lineno': 123,
                    'request_data': '{"max_tokens":1000,"messages":[{"role":"user","content":"What is four plus five?"}],"model":"claude-3-haiku-20240307","stream":true,"system":"You are a helpful assistant."}',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': IsJson(
                        [{'role': 'user', 'parts': [{'type': 'text', 'content': 'What is four plus five?'}]}]
                    ),
                    'gen_ai.system_instructions': IsJson([{'type': 'text', 'content': 'You are a helpful assistant.'}]),
                    'async': True,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.request.max_tokens":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
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
                    'request_data': '{"max_tokens":1000,"messages":[{"role":"user","content":"What is four plus five?"}],"model":"claude-3-haiku-20240307","stream":true,"system":"You are a helpful assistant."}',
                    'async': True,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_async_messages_stream',
                    'code.lineno': 123,
                    'logfire.msg': "streaming response from 'claude-3-haiku-20240307' took 1.00s",
                    'logfire.span_type': 'log',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': IsJson(
                        [{'role': 'user', 'parts': [{'type': 'text', 'content': 'What is four plus five?'}]}]
                    ),
                    'gen_ai.system_instructions': IsJson([{'type': 'text', 'content': 'You are a helpful assistant.'}]),
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': '{"combined_chunk_content":"The answer is secret","chunk_count":2}',
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.request.max_tokens":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{},"response_data":{"type":"object"}}}',
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
                },
            },
        ]
    )


def test_tool_messages(instrumented_client: anthropic.Anthropic, exporter: TestExporter):
    response = instrumented_client.messages.create(
        max_tokens=1000,
        model='claude-3-haiku-20240307',
        system='tool response',
        messages=[],
    )
    content = response.content[0]
    assert content.input == {'param': 'param'}  # type: ignore
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Message with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_tool_messages',
                    'code.lineno': 123,
                    'request_data': {
                        'max_tokens': 1000,
                        'messages': [],
                        'model': 'claude-3-haiku-20240307',
                        'system': 'tool response',
                    },
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': [],
                    'gen_ai.system_instructions': [{'type': 'text', 'content': 'tool response'}],
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'response_data': {
                        'message': {
                            'role': 'assistant',
                            'tool_calls': [
                                {'id': 'id', 'function': {'arguments': '{"input":{"param":"param"}}', 'name': 'tool'}}
                            ],
                        },
                        'usage': IsPartialDict(
                            {
                                'cache_creation': None,
                                'cache_creation_input_tokens': None,
                                'cache_read_input_tokens': None,
                                'input_tokens': 2,
                                'output_tokens': 3,
                                'server_tool_use': None,
                                'service_tier': None,
                            }
                        ),
                    },
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
                    'gen_ai.response.id': 'test_id',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 3,
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {'type': 'tool_call', 'id': 'id', 'name': 'tool', 'arguments': {'param': 'param'}}
                            ],
                        }
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.request.max_tokens': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.system_instructions': {'type': 'array'},
                            'async': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'usage': {'type': 'object', 'title': 'Usage', 'x-python-datatype': 'PydanticModel'}
                                },
                            },
                            'gen_ai.response.model': {},
                            'gen_ai.response.id': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


def test_unknown_method(instrumented_client: anthropic.Anthropic, exporter: TestExporter) -> None:
    response = instrumented_client.completions.create(max_tokens_to_sample=1000, model='claude-2.1', prompt='prompt')
    assert response.completion == 'completion'
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Anthropic API call to {url!r}',
                'context': {'is_remote': False, 'span_id': 1, 'trace_id': 1},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'request_data': '{"max_tokens_to_sample":1000,"model":"claude-2.1","prompt":"prompt"}',
                    'url': '/v1/complete',
                    'async': False,
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.request.model': 'claude-2.1',
                    'logfire.msg_template': 'Anthropic API call to {url!r}',
                    'logfire.msg': "Anthropic API call to '/v1/complete'",
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_unknown_method',
                    'code.lineno': 123,
                    'logfire.json_schema': IsStr(),
                    'gen_ai.response.model': 'claude-2.1',
                },
            }
        ]
    )


def test_request_parameters(instrumented_client: anthropic.Anthropic, exporter: TestExporter) -> None:
    """Test that all request parameters are extracted and added to span attributes."""
    tools: list[Any] = [
        {
            'name': 'get_weather',
            'description': 'Get the current weather',
            'input_schema': {
                'type': 'object',
                'properties': {'location': {'type': 'string'}},
                'required': ['location'],
            },
        }
    ]
    response = instrumented_client.messages.create(
        max_tokens=1000,
        model='claude-3-haiku-20240307',
        system='You are a helpful assistant.',
        messages=[{'role': 'user', 'content': 'What is four plus five?'}],
        temperature=0.7,
        top_p=0.9,
        top_k=40,
        stop_sequences=['END', 'STOP'],
        tools=cast(Any, tools),
    )
    assert isinstance(response.content[0], TextBlock)
    assert response.content[0].text == 'Nine'

    spans = exporter.exported_spans_as_dict()
    assert len(spans) == 1
    attributes = spans[0]['attributes']

    # Verify all request parameters are present
    assert attributes['gen_ai.request.max_tokens'] == 1000
    assert attributes['gen_ai.request.temperature'] == 0.7
    assert attributes['gen_ai.request.top_p'] == 0.9
    assert attributes['gen_ai.request.top_k'] == 40
    assert attributes['gen_ai.request.stop_sequences'] == '["END", "STOP"]'
    assert attributes['gen_ai.tool.definitions'] == IsJson(tools)


def test_extract_request_parameters_without_max_tokens() -> None:
    """Test _extract_request_parameters when max_tokens is not in json_data (covers branch 37->40)."""
    from logfire._internal.integrations.llm_providers.anthropic import (
        _extract_request_parameters,  # pyright: ignore[reportPrivateUsage]
    )

    # Test with no max_tokens - covers the branch where max_tokens is None
    json_data: dict[str, Any] = {'temperature': 0.5}
    span_data: dict[str, Any] = {}
    _extract_request_parameters(json_data, span_data)

    assert span_data.get('gen_ai.request.temperature') == 0.5
    assert 'gen_ai.request.max_tokens' not in span_data


def test_sync_messages_with_image_content(instrumented_client: anthropic.Anthropic, exporter: TestExporter) -> None:
    """Test messages with image content in user message."""
    response = instrumented_client.messages.create(
        max_tokens=1000,
        model='claude-3-haiku-20240307',
        system='image content',
        messages=[
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'What is in this image?'},
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': 'image/jpeg',
                            'data': 'base64encodeddata',
                        },
                    },
                ],
            }
        ],
    )
    assert isinstance(response.content[0], TextBlock)
    assert response.content[0].text == 'I can see a cat in the image.'

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Message with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_sync_messages_with_image_content',
                    'code.lineno': 123,
                    'request_data': {
                        'max_tokens': 1000,
                        'system': 'image content',
                        'messages': [
                            {
                                'role': 'user',
                                'content': [
                                    {'type': 'text', 'text': 'What is in this image?'},
                                    {
                                        'type': 'image',
                                        'source': {
                                            'type': 'base64',
                                            'media_type': 'image/jpeg',
                                            'data': 'base64encodeddata',
                                        },
                                    },
                                ],
                            }
                        ],
                        'model': 'claude-3-haiku-20240307',
                    },
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': [
                        {
                            'role': 'user',
                            'parts': [
                                {'type': 'text', 'content': 'What is in this image?'},
                                {
                                    'type': 'blob',
                                    'modality': 'image',
                                    'content': 'base64encodeddata',
                                    'media_type': 'image/jpeg',
                                },
                            ],
                        }
                    ],
                    'gen_ai.system_instructions': [{'type': 'text', 'content': 'image content'}],
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'response_data': {
                        'message': {
                            'content': 'I can see a cat in the image.',
                            'role': 'assistant',
                        },
                        'usage': IsPartialDict(
                            {
                                'cache_creation': None,
                                'input_tokens': 100,
                                'output_tokens': 8,
                            }
                        ),
                    },
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
                    'gen_ai.response.id': 'test_image_id',
                    'gen_ai.usage.input_tokens': 100,
                    'gen_ai.usage.output_tokens': 8,
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'I can see a cat in the image.'}]}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.request.max_tokens': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.system_instructions': {'type': 'array'},
                            'async': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'usage': {
                                        'type': 'object',
                                        'title': 'Usage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                            'gen_ai.response.model': {},
                            'gen_ai.response.id': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


def test_sync_messages_with_tool_use_conversation(
    instrumented_client: anthropic.Anthropic, exporter: TestExporter
) -> None:
    """Test messages with tool_use in assistant message and tool_result in user message."""
    response = instrumented_client.messages.create(
        max_tokens=1000,
        model='claude-3-haiku-20240307',
        system='tool use conversation',
        messages=[
            {'role': 'user', 'content': 'What is the weather in Boston?'},
            {
                'role': 'assistant',
                'content': [
                    {
                        'type': 'tool_use',
                        'id': 'tool_use_abc123',
                        'name': 'get_weather',
                        'input': {'location': 'Boston, MA'},
                    }
                ],
            },
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': 'tool_use_abc123',
                        'content': '{"temperature": 72, "condition": "sunny"}',
                    }
                ],
            },
        ],
    )
    assert isinstance(response.content[0], TextBlock)
    assert response.content[0].text == 'The weather in Boston is sunny and 72°F.'

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Message with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_sync_messages_with_tool_use_conversation',
                    'code.lineno': 123,
                    'request_data': {
                        'max_tokens': 1000,
                        'system': 'tool use conversation',
                        'messages': [
                            {'role': 'user', 'content': 'What is the weather in Boston?'},
                            {
                                'role': 'assistant',
                                'content': [
                                    {
                                        'type': 'tool_use',
                                        'id': 'tool_use_abc123',
                                        'name': 'get_weather',
                                        'input': {'location': 'Boston, MA'},
                                    }
                                ],
                            },
                            {
                                'role': 'user',
                                'content': [
                                    {
                                        'type': 'tool_result',
                                        'tool_use_id': 'tool_use_abc123',
                                        'content': '{"temperature": 72, "condition": "sunny"}',
                                    }
                                ],
                            },
                        ],
                        'model': 'claude-3-haiku-20240307',
                    },
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'What is the weather in Boston?'}]},
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'tool_call',
                                    'id': 'tool_use_abc123',
                                    'name': 'get_weather',
                                    'arguments': {'location': 'Boston, MA'},
                                }
                            ],
                        },
                        {
                            'role': 'user',
                            'parts': [
                                {
                                    'type': 'tool_call_response',
                                    'id': 'tool_use_abc123',
                                    'response': '{"temperature": 72, "condition": "sunny"}',
                                }
                            ],
                        },
                    ],
                    'gen_ai.system_instructions': [{'type': 'text', 'content': 'tool use conversation'}],
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'response_data': {
                        'message': {
                            'content': 'The weather in Boston is sunny and 72°F.',
                            'role': 'assistant',
                        },
                        'usage': IsPartialDict(
                            {
                                'cache_creation': None,
                                'input_tokens': 50,
                                'output_tokens': 15,
                            }
                        ),
                    },
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
                    'gen_ai.response.id': 'test_tool_conv_id',
                    'gen_ai.usage.input_tokens': 50,
                    'gen_ai.usage.output_tokens': 15,
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [{'type': 'text', 'content': 'The weather in Boston is sunny and 72°F.'}],
                        }
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.request.max_tokens': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.system_instructions': {'type': 'array'},
                            'async': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'usage': {
                                        'type': 'object',
                                        'title': 'Usage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                            'gen_ai.response.model': {},
                            'gen_ai.response.id': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )
