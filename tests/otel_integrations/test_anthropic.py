from __future__ import annotations as _annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

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
from logfire._internal.integrations.llm_providers.anthropic import content_from_messages
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
                    'gen_ai.input.messages': '[{"role":"user","parts":[{"type":"text","content":"What is four plus five?"}]}]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"You are a helpful assistant."}]',
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
                    'gen_ai.output.messages': '[{"role":"assistant","parts":[{"type":"text","content":"Nine"}]}]',
                    'logfire.json_schema': IsJson(
                        snapshot(
                            {
                                'type': 'object',
                                'properties': {
                                    'request_data': {'type': 'object'},
                                    'gen_ai.provider.name': {},
                                    'gen_ai.operation.name': {},
                                    'gen_ai.request.model': {},
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
                    'gen_ai.input.messages': '[{"role":"user","parts":[{"type":"text","content":"What is four plus five?"}]}]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"You are a helpful assistant."}]',
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
                    'gen_ai.output.messages': '[{"role":"assistant","parts":[{"type":"text","content":"Nine"}]}]',
                    'logfire.json_schema': IsJson(
                        {
                            'type': 'object',
                            'properties': {
                                'request_data': {'type': 'object'},
                                'gen_ai.provider.name': {},
                                'gen_ai.operation.name': {},
                                'gen_ai.request.model': {},
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
                    'gen_ai.input.messages': '[]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"empty response chunk"}]',
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{}}}',
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
                    'gen_ai.input.messages': '[]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"empty response chunk"}]',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': '{"combined_chunk_content":"","chunk_count":0}',
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{},"response_data":{"type":"object"}}}',
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
                    'gen_ai.input.messages': '[{"role":"user","parts":[{"type":"text","content":"What is four plus five?"}]}]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"You are a helpful assistant."}]',
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{}}}',
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
                    'gen_ai.input.messages': '[{"role":"user","parts":[{"type":"text","content":"What is four plus five?"}]}]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"You are a helpful assistant."}]',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': '{"combined_chunk_content":"The answer is secret","chunk_count":2}',
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{},"response_data":{"type":"object"}}}',
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
                    'gen_ai.input.messages': '[{"role":"user","parts":[{"type":"text","content":"What is four plus five?"}]}]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"You are a helpful assistant."}]',
                    'async': True,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{}}}',
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
                    'gen_ai.input.messages': '[{"role":"user","parts":[{"type":"text","content":"What is four plus five?"}]}]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"You are a helpful assistant."}]',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': '{"combined_chunk_content":"The answer is secret","chunk_count":2}',
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"request_data":{"type":"object"},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"async":{},"response_data":{"type":"object"}}}',
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
                            'tool_calls': [{'function': {'arguments': '{"input":{"param":"param"}}', 'name': 'tool'}}],
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


def test_sync_messages_latest(exporter: TestExporter) -> None:
    with httpx.Client(transport=MockTransport(request_handler)) as httpx_client:
        anthropic_client = anthropic.Anthropic(api_key='foobar', http_client=httpx_client)
        with logfire.instrument_anthropic(anthropic_client, version='latest'):
            response = anthropic_client.messages.create(
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
                'name': 'Message with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_sync_messages_latest',
                    'code.lineno': 123,
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.input.messages': '[{"role":"user","parts":[{"type":"text","content":"What is four plus five?"}]}]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"You are a helpful assistant."}]',
                    'request_data': '{"model":"claude-3-haiku-20240307"}',
                    'async': False,
                    'logfire.msg_template': 'Message with {gen_ai.request.model!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
                    'gen_ai.response.id': 'test_id',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 3,
                    'gen_ai.output.messages': '[{"role":"assistant","parts":[{"type":"text","content":"Nine"}]}]',
                    'logfire.json_schema': '{"type":"object","properties":{"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"request_data":{"type":"object"},"async":{},"gen_ai.response.model":{},"gen_ai.response.id":{},"gen_ai.usage.input_tokens":{},"gen_ai.usage.output_tokens":{},"gen_ai.output.messages":{"type":"array"}}}',
                },
            }
        ]
    )


async def test_async_messages_latest(exporter: TestExporter) -> None:
    async with httpx.AsyncClient(transport=MockTransport(request_handler)) as httpx_client:
        anthropic_client = anthropic.AsyncAnthropic(api_key='foobar', http_client=httpx_client)
        with logfire.instrument_anthropic(anthropic_client, version='latest'):
            response = await anthropic_client.messages.create(
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
                'name': 'Message with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_async_messages_latest',
                    'code.lineno': 123,
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.input.messages': '[{"role":"user","parts":[{"type":"text","content":"What is four plus five?"}]}]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"You are a helpful assistant."}]',
                    'request_data': '{"model":"claude-3-haiku-20240307"}',
                    'async': True,
                    'logfire.msg_template': 'Message with {gen_ai.request.model!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
                    'gen_ai.response.id': 'test_id',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 3,
                    'gen_ai.output.messages': '[{"role":"assistant","parts":[{"type":"text","content":"Nine"}]}]',
                    'logfire.json_schema': '{"type":"object","properties":{"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"request_data":{"type":"object"},"async":{},"gen_ai.response.model":{},"gen_ai.response.id":{},"gen_ai.usage.input_tokens":{},"gen_ai.usage.output_tokens":{},"gen_ai.output.messages":{"type":"array"}}}',
                },
            }
        ]
    )


def test_sync_messages_stream_latest(exporter: TestExporter) -> None:
    with httpx.Client(transport=MockTransport(request_handler)) as httpx_client:
        anthropic_client = anthropic.Anthropic(api_key='foobar', http_client=httpx_client)
        with logfire.instrument_anthropic(anthropic_client, version='latest'):
            response = anthropic_client.messages.create(
                max_tokens=1000,
                model='claude-3-haiku-20240307',
                system='You are a helpful assistant.',
                messages=[{'role': 'user', 'content': 'What is four plus five?'}],
                stream=True,
            )
            combined = ''.join(chunk for chunk in [content_from_messages(e) for e in response] if chunk is not None)
    assert combined == 'The answer is secret'
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Message with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_sync_messages_stream_latest',
                    'code.lineno': 123,
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.input.messages': '[{"role":"user","parts":[{"type":"text","content":"What is four plus five?"}]}]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"You are a helpful assistant."}]',
                    'request_data': '{"model":"claude-3-haiku-20240307"}',
                    'async': False,
                    'logfire.msg_template': 'Message with {gen_ai.request.model!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.json_schema': '{"type":"object","properties":{"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"request_data":{"type":"object"},"async":{}}}',
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
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
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'logfire.msg': "streaming response from 'claude-3-haiku-20240307' took 1.00s",
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_sync_messages_stream_latest',
                    'code.lineno': 123,
                    'duration': 1.0,
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'claude-3-haiku-20240307',
                    'gen_ai.input.messages': '[{"role":"user","parts":[{"type":"text","content":"What is four plus five?"}]}]',
                    'gen_ai.system_instructions': '[{"type":"text","content":"You are a helpful assistant."}]',
                    'request_data': '{"model":"claude-3-haiku-20240307"}',
                    'async': False,
                    'gen_ai.output.messages': '[{"role":"assistant","parts":[{"type":"text","content":"The answer is secret"}]}]',
                    'logfire.json_schema': '{"type":"object","properties":{"duration":{},"gen_ai.provider.name":{},"gen_ai.operation.name":{},"gen_ai.request.model":{},"gen_ai.input.messages":{"type":"array"},"gen_ai.system_instructions":{"type":"array"},"request_data":{"type":"object"},"async":{},"gen_ai.output.messages":{"type":"array"}}}',
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'claude-3-haiku-20240307',
                },
            },
        ]
    )


# --- Unit tests for semconv conversion functions ---


def test_convert_anthropic_content_part() -> None:
    """Test _convert_anthropic_content_part with all content part types."""
    from logfire._internal.integrations.llm_providers.anthropic import (
        _convert_anthropic_content_part,  # pyright: ignore[reportPrivateUsage]
    )

    # String
    assert _convert_anthropic_content_part('hello') == {'type': 'text', 'content': 'hello'}

    # Text block
    assert _convert_anthropic_content_part({'type': 'text', 'text': 'world'}) == {'type': 'text', 'content': 'world'}

    # Image with base64 source
    assert _convert_anthropic_content_part(
        {
            'type': 'image',
            'source': {'type': 'base64', 'data': 'abc123', 'media_type': 'image/png'},
        }
    ) == {'type': 'blob', 'modality': 'image', 'content': 'abc123', 'media_type': 'image/png'}

    # Image with URL source
    assert _convert_anthropic_content_part(
        {
            'type': 'image',
            'source': {'type': 'url', 'url': 'https://example.com/img.png'},
        }
    ) == {'type': 'uri', 'modality': 'image', 'uri': 'https://example.com/img.png'}

    # Image with unknown source type
    assert _convert_anthropic_content_part(
        {
            'type': 'image',
            'source': {'type': 'other'},
        }
    ) == {'type': 'image', 'source': {'type': 'other'}}

    # Tool use
    assert _convert_anthropic_content_part(
        {
            'type': 'tool_use',
            'id': 'tool_1',
            'name': 'search',
            'input': {'query': 'test'},
        }
    ) == {'type': 'tool_call', 'id': 'tool_1', 'name': 'search', 'arguments': {'query': 'test'}}

    # Tool result with list content (text + string)
    assert _convert_anthropic_content_part(
        {
            'type': 'tool_result',
            'tool_use_id': 'tool_1',
            'content': [{'type': 'text', 'text': 'result1'}, 'plain text'],
        }
    ) == {'type': 'tool_call_response', 'id': 'tool_1', 'response': 'result1 plain text'}

    # Tool result with string content
    assert _convert_anthropic_content_part(
        {
            'type': 'tool_result',
            'tool_use_id': 'tool_1',
            'content': 'simple result',
        }
    ) == {'type': 'tool_call_response', 'id': 'tool_1', 'response': 'simple result'}

    # Tool result with None content
    assert _convert_anthropic_content_part(
        {
            'type': 'tool_result',
            'tool_use_id': 'tool_1',
        }
    ) == {'type': 'tool_call_response', 'id': 'tool_1', 'response': ''}

    # Generic/unknown type
    assert _convert_anthropic_content_part(
        {
            'type': 'custom',
            'foo': 'bar',
        }
    ) == {'type': 'custom', 'foo': 'bar'}


def test_convert_anthropic_messages_to_semconv_complex() -> None:
    """Test conversion with system as list and content as list."""
    from logfire._internal.integrations.llm_providers.anthropic import convert_anthropic_messages_to_semconv

    messages: list[dict[str, Any]] = [
        # User with list content
        {'role': 'user', 'content': [{'type': 'text', 'text': 'Hello'}]},
        # Assistant with no content
        {'role': 'assistant'},
    ]
    # System as list of blocks including non-text type
    system: list[dict[str, Any]] = [
        {'type': 'text', 'text': 'Be helpful'},
        {'type': 'custom', 'data': 'value'},
    ]

    input_msgs, sys_inst = convert_anthropic_messages_to_semconv(messages, system)

    assert sys_inst == [
        {'type': 'text', 'content': 'Be helpful'},
        {'type': 'custom', 'data': 'value'},
    ]
    assert len(input_msgs) == 2
    assert input_msgs[0] == {'role': 'user', 'parts': [{'type': 'text', 'content': 'Hello'}]}
    assert input_msgs[1] == {'role': 'assistant', 'parts': []}

    # No system, no messages
    input_msgs, sys_inst = convert_anthropic_messages_to_semconv([])
    assert input_msgs == []
    assert sys_inst == []


def test_convert_anthropic_response_to_semconv_with_stop_reason() -> None:
    """Test response conversion with stop_reason."""
    from logfire._internal.integrations.llm_providers.anthropic import convert_anthropic_response_to_semconv

    message = Message(
        id='msg_1',
        content=[
            TextBlock(text='Let me search', type='text'),
        ],
        model='claude-3',
        role='assistant',
        type='message',
        usage=Usage(input_tokens=10, output_tokens=20),
        stop_reason='end_turn',
    )

    result = convert_anthropic_response_to_semconv(message)
    assert result == {
        'role': 'assistant',
        'parts': [{'type': 'text', 'content': 'Let me search'}],
        'finish_reason': 'end_turn',
    }


def test_anthropic_get_endpoint_config_non_messages_url_latest() -> None:
    """Test get_endpoint_config for non-/v1/messages URL with version='latest'."""
    from unittest.mock import MagicMock

    from logfire._internal.integrations.llm_providers.anthropic import get_endpoint_config

    options = MagicMock()
    options.url = '/v1/complete'
    options.json_data = {'model': 'claude-2.1', 'prompt': 'Hello'}

    config = get_endpoint_config(options, version='latest')
    assert config.message_template == 'Anthropic API call to {url!r}'
    assert config.span_data['url'] == '/v1/complete'
    assert config.span_data['gen_ai.provider.name'] == 'anthropic'
    assert config.span_data['gen_ai.request.model'] == 'claude-2.1'
    assert config.span_data['request_data'] == {'model': 'claude-2.1'}

    # Without model
    options.json_data = {'prompt': 'Hello'}
    config = get_endpoint_config(options, version='latest')
    assert 'gen_ai.request.model' not in config.span_data
    assert config.span_data['request_data'] == {}


def test_anthropic_get_endpoint_config_empty_messages() -> None:
    """Test get_endpoint_config for /v1/messages with no messages (covers branch misses)."""
    from unittest.mock import MagicMock

    from logfire._internal.integrations.llm_providers.anthropic import get_endpoint_config

    options = MagicMock()
    options.url = '/v1/messages'
    options.json_data = {'model': 'claude-3', 'messages': []}

    # version='latest' with no messages → no input_messages or system_instructions
    config = get_endpoint_config(options, version='latest')
    assert 'gen_ai.input.messages' not in config.span_data
    assert 'gen_ai.system_instructions' not in config.span_data

    # version='latest' with messages but no system → input_messages but no system_instructions
    options.json_data = {'model': 'claude-3', 'messages': [{'role': 'user', 'content': 'hi'}]}
    config = get_endpoint_config(options, version='latest')
    assert 'gen_ai.input.messages' in config.span_data
    assert 'gen_ai.system_instructions' not in config.span_data

    # version=1 with no messages
    options.json_data = {'model': 'claude-3', 'messages': []}
    config = get_endpoint_config(options, version=1)
    assert 'gen_ai.input.messages' not in config.span_data

    # version=1 with messages but no system
    options.json_data = {'model': 'claude-3', 'messages': [{'role': 'user', 'content': 'hi'}]}
    config = get_endpoint_config(options, version=1)
    assert 'gen_ai.input.messages' in config.span_data
    assert 'gen_ai.system_instructions' not in config.span_data

    # version=1 non-messages URL without model
    options.url = '/v1/complete'
    options.json_data = {'prompt': 'Hello'}
    config = get_endpoint_config(options, version=1)
    assert 'gen_ai.request.model' not in config.span_data


def test_sync_messages_latest_with_stop_reason(exporter: TestExporter) -> None:
    """Test that stop_reason is captured as finish_reason and RESPONSE_FINISH_REASONS."""

    def handler_with_stop_reason(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=Message(
                id='test_id',
                content=[TextBlock(text='Nine', type='text')],
                model='claude-3-haiku-20240307',
                role='assistant',
                type='message',
                usage=Usage(input_tokens=2, output_tokens=3),
                stop_reason='end_turn',
            ).model_dump(mode='json'),
        )

    with httpx.Client(transport=MockTransport(handler_with_stop_reason)) as httpx_client:
        anthropic_client = anthropic.Anthropic(api_key='foobar', http_client=httpx_client)
        with logfire.instrument_anthropic(anthropic_client, version='latest'):
            response = anthropic_client.messages.create(
                model='claude-3-haiku-20240307',
                max_tokens=1000,
                system='You are a helpful assistant.',
                messages=[{'role': 'user', 'content': 'What is four plus five?'}],
            )
    assert response.content[0].text == 'Nine'  # type: ignore
    result = exporter.exported_spans_as_dict(parse_json_attributes=True)
    span = result[0]['attributes']
    # Verify stop_reason appears in the output message as finish_reason
    assert span['gen_ai.output.messages'][0].get('finish_reason') == 'end_turn'
    # Verify RESPONSE_FINISH_REASONS is set
    assert span['gen_ai.response.finish_reasons'] == ['end_turn']
