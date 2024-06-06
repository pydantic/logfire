from __future__ import annotations as _annotations

import json
from typing import AsyncIterator, Iterator

import anthropic
import httpx
import pytest
from anthropic._models import FinalRequestOptions
from anthropic.types import (
    Completion,
    Message,
    MessageDeltaUsage,
    MessageStartEvent,
    MessageStopEvent,
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
    RawContentBlockStopEvent,
    RawMessageDeltaEvent,
    TextBlock,
    TextDelta,
    ToolUseBlock,
    Usage,
)
from anthropic.types.raw_message_delta_event import Delta
from dirty_equals import IsJson
from dirty_equals._strings import IsStr
from httpx._transports.mock import MockTransport
from inline_snapshot import snapshot

import logfire
from logfire._internal.integrations.llm_providers.anthropic import get_endpoint_config
from logfire.testing import TestExporter


def request_handler(request: httpx.Request) -> httpx.Response:
    """Used to mock httpx requests

    We do this instead of using pytest-httpx since 1) it's nearly as simple 2) pytest-httpx doesn't support Python 3.8.
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
                RawContentBlockStartEvent(
                    content_block=TextBlock(text='', type='text'), index=0, type='content_block_start'
                ),
                RawContentBlockDeltaEvent(
                    delta=TextDelta(text='The answer', type='text_delta'), index=0, type='content_block_delta'
                ),
                RawContentBlockDeltaEvent(
                    delta=TextDelta(text=' is secret', type='text_delta'), index=0, type='content_block_delta'
                ),
                RawContentBlockStopEvent(index=0, type='content_block_stop'),
                RawMessageDeltaEvent(
                    delta=Delta(stop_reason='end_turn', stop_sequence=None),
                    type='message_delta',
                    usage=MessageDeltaUsage(output_tokens=55),
                ),
                MessageStopEvent(type='message_stop'),
            ]
            return httpx.Response(
                200, text=''.join(f'event: {chunk.type}\ndata: {chunk.model_dump_json()}\n\n' for chunk in chunks)
            )
    elif json_body['system'] == 'tool response':
        return httpx.Response(
            200,
            json=Message(
                id='test_id',
                content=[ToolUseBlock(id='id', input={'param': 'param'}, name='tool', type='tool_use')],
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
                        {
                            'max_tokens': 1000,
                            'system': 'You are a helpful assistant.',
                            'messages': [{'role': 'user', 'content': 'What is four plus five?'}],
                            'model': 'claude-3-haiku-20240307',
                        }
                    ),
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'response_data': IsJson(
                        {
                            'message': {
                                'content': 'Nine',
                                'role': 'assistant',
                            },
                            'usage': {'input_tokens': 2, 'output_tokens': 3},
                        }
                    ),
                    'logfire.json_schema': IsJson(
                        {
                            'type': 'object',
                            'properties': {
                                'request_data': {'type': 'object'},
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
                            },
                        }
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
                    'async': True,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'response_data': IsJson(
                        {
                            'message': {
                                'content': 'Nine',
                                'role': 'assistant',
                            },
                            'usage': {'input_tokens': 2, 'output_tokens': 3},
                        }
                    ),
                    'logfire.json_schema': IsJson(
                        {
                            'type': 'object',
                            'properties': {
                                'request_data': {'type': 'object'},
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
                            },
                        }
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
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"async":{}}}',
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
                    'request_data': '{"max_tokens":1000,"messages":[],"model":"claude-3-haiku-20240307","stream":true,"system":"empty response chunk"}',
                    'async': False,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_sync_message_empty_response_chunk',
                    'code.lineno': 123,
                    'logfire.msg': "streaming response from 'claude-3-haiku-20240307' took 1.00s",
                    'logfire.span_type': 'log',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': '{"combined_chunk_content":"","chunk_count":0}',
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"async":{},"duration":{},"response_data":{"type":"object"}}}',
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
            chunk.delta.text
            for chunk in stream
            if isinstance(chunk, RawContentBlockDeltaEvent) and isinstance(chunk.delta, TextDelta)
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
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"async":{}}}',
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
                    'request_data': '{"max_tokens":1000,"messages":[{"role":"user","content":"What is four plus five?"}],"model":"claude-3-haiku-20240307","stream":true,"system":"You are a helpful assistant."}',
                    'async': False,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'code.filepath': 'test_anthropic.py',
                    'code.function': '<genexpr>',
                    'code.lineno': 123,
                    'logfire.msg': "streaming response from 'claude-3-haiku-20240307' took 1.00s",
                    'logfire.span_type': 'log',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': '{"combined_chunk_content":"The answer is secret","chunk_count":3}',
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"async":{},"duration":{},"response_data":{"type":"object"}}}',
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
            chunk.delta.text
            async for chunk in stream
            if isinstance(chunk, RawContentBlockDeltaEvent) and isinstance(chunk.delta, TextDelta)
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
                    'async': True,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"async":{}}}',
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
                    'request_data': '{"max_tokens":1000,"messages":[{"role":"user","content":"What is four plus five?"}],"model":"claude-3-haiku-20240307","stream":true,"system":"You are a helpful assistant."}',
                    'async': True,
                    'logfire.msg_template': 'streaming response from {request_data[model]!r} took {duration:.2f}s',
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_async_messages_stream',
                    'code.lineno': 123,
                    'logfire.msg': "streaming response from 'claude-3-haiku-20240307' took 1.00s",
                    'logfire.span_type': 'log',
                    'logfire.tags': ('LLM',),
                    'duration': 1.0,
                    'response_data': '{"combined_chunk_content":"The answer is secret","chunk_count":3}',
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"async":{},"duration":{},"response_data":{"type":"object"}}}',
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
    assert isinstance(response.content[0], ToolUseBlock)
    content = response.content[0]
    assert isinstance(content, ToolUseBlock)
    assert content.input == {'param': 'param'}
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
                    'code.function': 'test_tool_messages',
                    'code.lineno': 123,
                    'request_data': '{"max_tokens":1000,"messages":[],"model":"claude-3-haiku-20240307","system":"tool response"}',
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'claude-3-haiku-20240307'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'response_data': '{"message":{"role":"assistant","tool_calls":[{"function":{"arguments":"{\\"input\\":{\\"param\\":\\"param\\"}}","name":"tool"}}]},"usage":{"input_tokens":2,"output_tokens":3}}',
                    'logfire.json_schema': '{"type":"object","properties":{"request_data":{"type":"object"},"async":{},"response_data":{"type":"object","properties":{"usage":{"type":"object","title":"Usage","x-python-datatype":"PydanticModel"}}}}}',
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
                'name': 'Unable to instrument {suffix} API call: {error}',
                'context': {'is_remote': False, 'span_id': 1, 'trace_id': 1},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.tags': ('LLM',),
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Unable to instrument {suffix} API call: {error}',
                    'logfire.msg': 'Unable to instrument Anthropic API call: Unknown Anthropic API endpoint: `/v1/complete`',
                    'code.filepath': 'test_anthropic.py',
                    'code.function': 'test_unknown_method',
                    'code.lineno': 123,
                    'error': 'Unknown Anthropic API endpoint: `/v1/complete`',
                    'kwargs': IsStr(),
                    'logfire.json_schema': IsStr(),
                    'suffix': 'Anthropic',
                },
            }
        ]
    )


def test_get_endpoint_config_json_not_dict():
    with pytest.raises(ValueError, match='Expected `options.json_data` to be a dictionary'):
        get_endpoint_config(FinalRequestOptions(method='POST', url='...'))


def test_get_endpoint_config_unknown_url():
    with pytest.raises(ValueError, match='Unknown Anthropic API endpoint: `/foobar/`'):
        get_endpoint_config(FinalRequestOptions(method='POST', url='/foobar/', json_data={'model': 'foobar'}))
