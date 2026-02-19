# pyright: reportCallIssue=false, reportArgumentType=false, reportPrivateUsage=false
from __future__ import annotations as _annotations

from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from typing import Any

import pytest
from azure.ai.inference.models import (
    ChatChoice,
    ChatCompletions,
    ChatResponseMessage,
    CompletionsUsage,
    EmbeddingItem,
    EmbeddingsResult,
    EmbeddingsUsage,
    StreamingChatChoiceUpdate,
    StreamingChatCompletionsUpdate,
    StreamingChatResponseMessageUpdate,
)
from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter


def _make_chat_response(
    content: str = 'Nine',
    finish_reason: str = 'stop',
    tool_calls: list[Any] | None = None,
) -> ChatCompletions:
    message_kwargs: dict[str, Any] = {'role': 'assistant', 'content': content}
    if tool_calls is not None:
        message_kwargs['tool_calls'] = tool_calls
    return ChatCompletions(
        id='test-id',
        model='gpt-4',
        created=datetime(2024, 1, 1),
        choices=[
            ChatChoice(
                index=0,
                finish_reason=finish_reason,
                message=ChatResponseMessage(**message_kwargs),
            )
        ],
        usage=CompletionsUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _make_tool_response() -> ChatCompletions:
    return _make_chat_response(
        content='',
        finish_reason='tool_calls',
        tool_calls=[
            {
                'id': 'call_1',
                'type': 'function',
                'function': {'name': 'get_weather', 'arguments': '{"city": "London"}'},
            }
        ],
    )


def _make_streaming_chunks() -> list[StreamingChatCompletionsUpdate]:
    return [
        StreamingChatCompletionsUpdate(
            id='test-id',
            model='gpt-4',
            created=datetime(2024, 1, 1),
            choices=[
                StreamingChatChoiceUpdate(
                    index=0, delta=StreamingChatResponseMessageUpdate(role='assistant', content='')
                )
            ],
        ),
        StreamingChatCompletionsUpdate(
            id='test-id',
            model='gpt-4',
            created=datetime(2024, 1, 1),
            choices=[
                StreamingChatChoiceUpdate(index=0, delta=StreamingChatResponseMessageUpdate(content='The answer'))
            ],
        ),
        StreamingChatCompletionsUpdate(
            id='test-id',
            model='gpt-4',
            created=datetime(2024, 1, 1),
            choices=[
                StreamingChatChoiceUpdate(index=0, delta=StreamingChatResponseMessageUpdate(content=' is secret'))
            ],
        ),
        StreamingChatCompletionsUpdate(
            id='test-id',
            model='gpt-4',
            created=datetime(2024, 1, 1),
            choices=[
                StreamingChatChoiceUpdate(
                    index=0, finish_reason='stop', delta=StreamingChatResponseMessageUpdate(content='')
                )
            ],
        ),
    ]


def _make_embed_response() -> EmbeddingsResult:
    return EmbeddingsResult(
        id='test-id',
        model='text-embedding-ada-002',
        data=[EmbeddingItem(embedding=[0.1, 0.2, 0.3], index=0)],
        usage=EmbeddingsUsage(prompt_tokens=5, total_tokens=5),
    )


class MockChatCompletionsClient:
    """Mock ChatCompletionsClient that returns preconfigured responses."""

    __module__ = 'azure.ai.inference'

    def __init__(self, response: Any = None, stream_chunks: list[Any] | None = None) -> None:
        self._response = response or _make_chat_response()
        self._stream_chunks = stream_chunks

    def complete(self, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get('stream'):
            return iter(self._stream_chunks or _make_streaming_chunks())
        return self._response


class MockAsyncChatCompletionsClient:
    """Mock async ChatCompletionsClient."""

    __module__ = 'azure.ai.inference.aio'

    def __init__(self, response: Any = None, stream_chunks: list[Any] | None = None) -> None:
        self._response = response or _make_chat_response()
        self._stream_chunks = stream_chunks

    async def complete(self, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get('stream'):
            return _async_iter(self._stream_chunks or _make_streaming_chunks())
        return self._response


class MockEmbeddingsClient:
    """Mock EmbeddingsClient."""

    __module__ = 'azure.ai.inference'

    def __init__(self, response: Any = None) -> None:
        self._response = response or _make_embed_response()

    def embed(self, **kwargs: Any) -> Any:
        return self._response


class MockAsyncEmbeddingsClient:
    """Mock async EmbeddingsClient."""

    __module__ = 'azure.ai.inference.aio'

    def __init__(self, response: Any = None) -> None:
        self._response = response or _make_embed_response()

    async def embed(self, **kwargs: Any) -> Any:
        return self._response


async def _async_iter(items: list[Any]) -> Any:
    for item in items:
        yield item


def test_sync_chat(exporter: TestExporter) -> None:
    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        response = client.complete(
            model='gpt-4',
            messages=[
                {'role': 'system', 'content': 'You are helpful.'},
                {'role': 'user', 'content': 'What is four plus five?'},
            ],
            temperature=0.5,
        )
    assert response.choices[0].message.content == 'Nine'
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_azure_ai_inference.py',
                    'code.function': 'test_sync_chat',
                    'code.lineno': 123,
                    'request_data': {'model': 'gpt-4'},
                    'gen_ai.provider.name': 'azure.ai.inference',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.request.temperature': 0.5,
                    'gen_ai.input.messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'What is four plus five?'}]}
                    ],
                    'gen_ai.system_instructions': [{'type': 'text', 'content': 'You are helpful.'}],
                    'logfire.msg_template': 'Chat completion with {request_data[model]!r}',
                    'logfire.msg': "Chat completion with 'gpt-4'",
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [{'type': 'text', 'content': 'Nine'}],
                            'finish_reason': 'CompletionsFinishReason.STOPPED',
                        }
                    ],
                    'gen_ai.response.model': 'gpt-4',
                    'gen_ai.response.id': 'test-id',
                    'gen_ai.usage.input_tokens': 10,
                    'gen_ai.usage.output_tokens': 5,
                    'gen_ai.response.finish_reasons': ['CompletionsFinishReason.STOPPED'],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.request.temperature': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.system_instructions': {'type': 'array'},
                            'gen_ai.output.messages': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'role': {
                                            'type': 'string',
                                            'title': 'ChatRole',
                                            'x-python-datatype': 'Enum',
                                            'enum': ['system', 'user', 'assistant', 'tool', 'developer'],
                                        }
                                    },
                                },
                            },
                            'gen_ai.response.model': {},
                            'gen_ai.response.id': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'gen_ai.response.finish_reasons': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


def test_sync_chat_streaming(exporter: TestExporter) -> None:
    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        response = client.complete(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Tell me a secret'}],
            stream=True,
        )
        chunks = list(response)
    assert len(chunks) == 4
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_azure_ai_inference.py',
                    'code.function': 'test_sync_chat_streaming',
                    'code.lineno': 123,
                    'request_data': {'model': 'gpt-4'},
                    'gen_ai.provider.name': 'azure.ai.inference',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.input.messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'Tell me a secret'}]}
                    ],
                    'logfire.msg_template': 'Chat completion with {request_data[model]!r}',
                    'logfire.msg': "Chat completion with 'gpt-4'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.input.messages': {'type': 'array'},
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
                    'code.filepath': 'test_azure_ai_inference.py',
                    'code.function': 'test_sync_chat_streaming',
                    'code.lineno': 123,
                    'duration': 1.0,
                    'request_data': {'model': 'gpt-4'},
                    'gen_ai.provider.name': 'azure.ai.inference',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'gpt-4',
                    'gen_ai.input.messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'Tell me a secret'}]}
                    ],
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'The answer is secret'}]}
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'duration': {},
                            'request_data': {'type': 'object'},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'gen_ai.response.model': 'gpt-4',
                },
            },
        ]
    )


def test_sync_chat_tool_calls(exporter: TestExporter) -> None:
    client = MockChatCompletionsClient(response=_make_tool_response())
    with logfire.instrument_azure_ai_inference(client):
        client.complete(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'What is the weather?'}],
        )
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    attrs = spans[0]['attributes']
    # Check tool calls in semconv output
    output_msgs = attrs['gen_ai.output.messages']
    assert len(output_msgs) == 1
    tool_part = output_msgs[0]['parts'][0]
    assert tool_part['type'] == 'tool_call'
    assert tool_part['name'] == 'get_weather'


@pytest.mark.anyio
async def test_async_chat(exporter: TestExporter) -> None:
    client = MockAsyncChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        response = await client.complete(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'What is four plus five?'}],
        )
    assert response.choices[0].message.content == 'Nine'
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    assert spans[0]['attributes']['gen_ai.response.model'] == 'gpt-4'
    assert spans[0]['attributes']['gen_ai.usage.input_tokens'] == 10


@pytest.mark.anyio
async def test_async_chat_streaming(exporter: TestExporter) -> None:
    client = MockAsyncChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        response = await client.complete(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Tell me a secret'}],
            stream=True,
        )
        chunks = [chunk async for chunk in response]
    assert len(chunks) == 4
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 2
    # First span: the request
    assert spans[0]['attributes']['logfire.msg'] == "Chat completion with 'gpt-4'"
    # Second span: streaming info
    assert 'streaming response from' in spans[1]['attributes']['logfire.msg']


def test_sync_embeddings(exporter: TestExporter) -> None:
    client = MockEmbeddingsClient()
    with logfire.instrument_azure_ai_inference(client):
        response = client.embed(
            model='text-embedding-ada-002',
            input=['Hello world'],
        )
    assert len(response.data) == 1
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    attrs = spans[0]['attributes']
    assert attrs['gen_ai.provider.name'] == 'azure.ai.inference'
    assert attrs['gen_ai.operation.name'] == 'embeddings'
    assert attrs['gen_ai.request.model'] == 'text-embedding-ada-002'
    assert attrs['gen_ai.response.model'] == 'text-embedding-ada-002'
    assert attrs['gen_ai.usage.input_tokens'] == 5


@pytest.mark.anyio
async def test_async_embeddings(exporter: TestExporter) -> None:
    client = MockAsyncEmbeddingsClient()
    with logfire.instrument_azure_ai_inference(client):
        response = await client.embed(
            model='text-embedding-ada-002',
            input=['Hello world'],
        )
    assert len(response.data) == 1
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    assert spans[0]['attributes']['gen_ai.operation.name'] == 'embeddings'


def test_uninstrumentation(exporter: TestExporter) -> None:
    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        client.complete(model='gpt-4', messages=[{'role': 'user', 'content': 'Hi'}])
        assert len(exporter.exported_spans_as_dict()) == 1

    # After exiting context, client should be uninstrumented
    exporter.clear()
    client.complete(model='gpt-4', messages=[{'role': 'user', 'content': 'Hi'}])
    assert len(exporter.exported_spans_as_dict()) == 0


def test_double_instrumentation(exporter: TestExporter) -> None:
    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        with logfire.instrument_azure_ai_inference(client):
            client.complete(model='gpt-4', messages=[{'role': 'user', 'content': 'Hi'}])
    # Should only produce one span (not double-instrumented)
    assert len(exporter.exported_spans_as_dict()) == 1


def test_no_model_backfill(exporter: TestExporter) -> None:
    """When request has no model, backfill from response."""
    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        client.complete(
            messages=[{'role': 'user', 'content': 'Hi'}],
        )
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    attrs = spans[0]['attributes']
    # Model backfilled from response
    assert attrs['logfire.msg'] == "Chat completion with 'gpt-4'"
    assert attrs['gen_ai.request.model'] == 'gpt-4'
    assert attrs['gen_ai.response.model'] == 'gpt-4'


def test_no_model_streaming_backfill(exporter: TestExporter) -> None:
    """When streaming request has no model, backfill from first chunk."""
    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        response = client.complete(
            messages=[{'role': 'user', 'content': 'Hi'}],
            stream=True,
        )
        list(response)
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 2
    # Streaming info span should have model from chunks
    assert spans[1]['attributes']['request_data']['model'] == 'gpt-4'
    assert spans[1]['attributes']['gen_ai.request.model'] == 'gpt-4'


@pytest.mark.anyio
async def test_no_model_async_streaming_backfill(exporter: TestExporter) -> None:
    """When async streaming request has no model, backfill from first chunk."""
    client = MockAsyncChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        response = await client.complete(
            messages=[{'role': 'user', 'content': 'Hi'}],
            stream=True,
        )
        async for _ in response:
            pass
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 2
    assert spans[1]['attributes']['request_data']['model'] == 'gpt-4'


def test_no_model_embed_backfill(exporter: TestExporter) -> None:
    """When embed request has no model, backfill from response."""
    client = MockEmbeddingsClient()
    with logfire.instrument_azure_ai_inference(client):
        client.embed(input=['Hello'])
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    attrs = spans[0]['attributes']
    assert attrs['logfire.msg'] == "Embeddings with 'text-embedding-ada-002'"
    assert attrs['gen_ai.request.model'] == 'text-embedding-ada-002'


@pytest.mark.anyio
async def test_no_model_async_embed_backfill(exporter: TestExporter) -> None:
    """When async embed request has no model, backfill from response."""
    client = MockAsyncEmbeddingsClient()
    with logfire.instrument_azure_ai_inference(client):
        await client.embed(input=['Hello'])
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    assert attrs_msg(spans[0]) == "Embeddings with 'text-embedding-ada-002'"


def attrs_msg(span: dict[str, Any]) -> str:
    return span['attributes']['logfire.msg']


def test_suppress_false(exporter: TestExporter) -> None:
    """Test with suppress_other_instrumentation=False."""
    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client, suppress_other_instrumentation=False):
        client.complete(model='gpt-4', messages=[{'role': 'user', 'content': 'Hi'}])
    assert len(exporter.exported_spans_as_dict()) == 1


@pytest.mark.anyio
async def test_suppress_false_async(exporter: TestExporter) -> None:
    """Test with suppress_other_instrumentation=False for async."""
    client = MockAsyncChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client, suppress_other_instrumentation=False):
        await client.complete(model='gpt-4', messages=[{'role': 'user', 'content': 'Hi'}])
    assert len(exporter.exported_spans_as_dict()) == 1


def test_suppress_false_embed(exporter: TestExporter) -> None:
    """Test embed with suppress=False."""
    client = MockEmbeddingsClient()
    with logfire.instrument_azure_ai_inference(client, suppress_other_instrumentation=False):
        client.embed(model='text-embedding-ada-002', input=['Hi'])
    assert len(exporter.exported_spans_as_dict()) == 1


@pytest.mark.anyio
async def test_suppress_false_async_embed(exporter: TestExporter) -> None:
    """Test async embed with suppress=False."""
    client = MockAsyncEmbeddingsClient()
    with logfire.instrument_azure_ai_inference(client, suppress_other_instrumentation=False):
        await client.embed(model='text-embedding-ada-002', input=['Hi'])
    assert len(exporter.exported_spans_as_dict()) == 1


def test_list_instrumentation(exporter: TestExporter) -> None:
    """Test instrumenting a list of clients."""
    chat_client = MockChatCompletionsClient()
    embed_client = MockEmbeddingsClient()
    with logfire.instrument_azure_ai_inference([chat_client, embed_client]):
        chat_client.complete(model='gpt-4', messages=[{'role': 'user', 'content': 'Hi'}])
        embed_client.embed(model='text-embedding-ada-002', input=['Hello'])
    assert len(exporter.exported_spans_as_dict()) == 2

    # After exiting, both should be uninstrumented
    exporter.clear()
    chat_client.complete(model='gpt-4', messages=[{'role': 'user', 'content': 'Hi'}])
    embed_client.embed(model='text-embedding-ada-002', input=['Hello'])
    assert len(exporter.exported_spans_as_dict()) == 0


def test_request_parameters(exporter: TestExporter) -> None:
    """Test that all request parameters are captured."""
    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        client.complete(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Hi'}],
            temperature=0.7,
            max_tokens=100,
            top_p=0.9,
            frequency_penalty=0.5,
            presence_penalty=0.3,
            seed=42,
            stop=['\n', 'END'],
        )
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    attrs = spans[0]['attributes']
    assert attrs['gen_ai.request.temperature'] == 0.7
    assert attrs['gen_ai.request.max_tokens'] == 100
    assert attrs['gen_ai.request.top_p'] == 0.9
    assert attrs['gen_ai.request.frequency_penalty'] == 0.5
    assert attrs['gen_ai.request.presence_penalty'] == 0.3
    assert attrs['gen_ai.request.seed'] == 42
    assert attrs['gen_ai.request.stop_sequences'] == ['\n', 'END']


def test_extract_params_body_style(exporter: TestExporter) -> None:
    """Test that body-style parameters are extracted."""
    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        client.complete(body={'model': 'gpt-4', 'messages': [{'role': 'user', 'content': 'Hi'}]})
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert spans[0]['attributes']['gen_ai.request.model'] == 'gpt-4'


def test_content_item_conversion() -> None:
    """Test conversion of multimodal content items."""
    from logfire._internal.integrations.llm_providers.azure_ai_inference import convert_messages_to_semconv

    messages = [
        {
            'role': 'user',
            'content': [
                'plain string item',
                {'type': 'text', 'text': 'text item'},
                {'type': 'image_url', 'image_url': {'url': 'https://example.com/img.png'}},
                {'type': 'input_audio', 'input_audio': {'data': 'base64data', 'format': 'mp3'}},
            ],
        },
    ]
    input_msgs, _ = convert_messages_to_semconv(messages)
    parts = input_msgs[0]['parts']
    assert parts[0] == {'type': 'text', 'content': 'plain string item'}
    assert parts[1] == {'type': 'text', 'content': 'text item'}
    assert parts[2] == {'type': 'uri', 'uri': 'https://example.com/img.png', 'modality': 'image'}
    assert parts[3] == {'type': 'blob', 'content': 'base64data', 'media_type': 'audio/mp3', 'modality': 'audio'}


def test_stream_context_manager(exporter: TestExporter) -> None:
    """Test that sync stream wrapper supports context manager protocol."""
    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        response = client.complete(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Hi'}],
            stream=True,
        )
        # Use as context manager
        with response:
            for _ in response:
                pass
    assert len(exporter.exported_spans_as_dict()) == 2


@pytest.mark.anyio
async def test_async_stream_context_manager(exporter: TestExporter) -> None:
    """Test that async stream wrapper supports async context manager protocol."""
    client = MockAsyncChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        response = await client.complete(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Hi'}],
            stream=True,
        )
        async with response:
            async for _ in response:
                pass
    assert len(exporter.exported_spans_as_dict()) == 2


def test_positional_arg_extraction() -> None:
    """Test that _extract_params handles positional args correctly."""
    from logfire._internal.integrations.llm_providers.azure_ai_inference import _extract_params

    # Single positional arg with 'messages' key
    result = _extract_params(({'model': 'gpt-4', 'messages': [{'role': 'user', 'content': 'Hi'}]},), {})
    assert result['model'] == 'gpt-4'

    # Multiple args, first doesn't match, second does (covers loop iteration)
    result = _extract_params(('not-a-dict', {'messages': [{'role': 'user', 'content': 'Hi'}]}), {})
    assert 'messages' in result

    # No matching arg, falls back to kwargs
    result = _extract_params(('not-a-dict',), {'model': 'gpt-4'})
    assert result == {'model': 'gpt-4'}


def test_tools_with_as_dict(exporter: TestExporter) -> None:
    """Test that tool objects with as_dict() are handled."""

    class MockTool:
        def as_dict(self) -> dict[str, Any]:
            return {'type': 'function', 'function': {'name': 'my_tool', 'parameters': {}}}

    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        client.complete(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Hi'}],
            tools=[MockTool()],
        )
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    tool_defs = spans[0]['attributes']['gen_ai.tool.definitions']
    assert tool_defs == [{'type': 'function', 'function': {'name': 'my_tool', 'parameters': {}}}]


def test_backfill_no_model_in_response(exporter: TestExporter) -> None:
    """Test backfill when response also has no model."""
    response = ChatCompletions(
        id='test-id',
        model=None,
        created=datetime(2024, 1, 1),
        choices=[
            ChatChoice(
                index=0,
                finish_reason='stop',
                message=ChatResponseMessage(role='assistant', content='Hello'),
            )
        ],
        usage=CompletionsUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    client = MockChatCompletionsClient(response=response)
    with logfire.instrument_azure_ai_inference(client):
        client.complete(messages=[{'role': 'user', 'content': 'Hi'}])
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    # Model stays None - no backfill
    assert spans[0]['attributes']['logfire.msg'] == 'Chat completion'


def test_minimal_chat_response(exporter: TestExporter) -> None:
    """Test response with no model, no id, no usage, no finish_reason.

    Exercises the false branches in _on_chat_response.
    """
    response = ChatCompletions(
        id=None,
        model=None,
        created=datetime(2024, 1, 1),
        choices=[
            ChatChoice(
                index=0,
                finish_reason=None,
                message=ChatResponseMessage(role='assistant', content='Hi'),
            )
        ],
        usage=None,
    )
    client = MockChatCompletionsClient(response=response)
    with logfire.instrument_azure_ai_inference(client):
        client.complete(model='gpt-4', messages=[{'role': 'user', 'content': 'Hi'}])
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1


def test_choice_without_message() -> None:
    """Test response with a choice that has no message.

    Exercises the `if not message: continue` path in convert_response_to_semconv.
    """
    from logfire._internal.integrations.llm_providers.azure_ai_inference import convert_response_to_semconv

    class FakeChoice:
        message = None
        finish_reason = 'stop'

    class FakeResponse:
        choices = [FakeChoice()]

    output = convert_response_to_semconv(FakeResponse())
    assert output == []


def test_minimal_embed_response(exporter: TestExporter) -> None:
    """Test embed response with no model, no id, no usage.

    Exercises the false branches in _on_embed_response.
    """
    response = EmbeddingsResult(
        id=None,
        model=None,
        data=[EmbeddingItem(embedding=[0.1], index=0)],
        usage=None,
    )
    client = MockEmbeddingsClient(response=response)
    with logfire.instrument_azure_ai_inference(client):
        client.embed(model='text-embedding-ada-002', input=['Hi'])
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1


def test_response_empty_choices(exporter: TestExporter) -> None:
    """Test response with empty choices list.

    Exercises the false branch of `if output_messages:` in _on_chat_response.
    """

    class FakeResponse:
        id = 'test-id'
        model = 'gpt-4'
        choices: list[Any] = []
        usage = None

    client = MockChatCompletionsClient(response=FakeResponse())
    with logfire.instrument_azure_ai_inference(client):
        client.complete(model='gpt-4', messages=[{'role': 'user', 'content': 'Hi'}])
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1


def test_usage_with_none_tokens(exporter: TestExporter) -> None:
    """Test response with usage but None prompt/completion tokens.

    Exercises false branches of prompt_tokens/completion_tokens checks.
    """

    class FakeUsage:
        prompt_tokens = None
        completion_tokens = None

    class FakeMessage:
        role = 'assistant'
        content = 'Hi'
        tool_calls = None

    class FakeChoice:
        index = 0
        finish_reason = None
        message = FakeMessage()

    class FakeResponse:
        id = None
        model = None
        choices = [FakeChoice()]
        usage = FakeUsage()

    client = MockChatCompletionsClient(response=FakeResponse())
    with logfire.instrument_azure_ai_inference(client):
        client.complete(model='gpt-4', messages=[{'role': 'user', 'content': 'Hi'}])
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1


def test_embed_usage_with_none_tokens(exporter: TestExporter) -> None:
    """Test embed response with usage but None prompt_tokens.

    Exercises false branch of prompt_tokens check in _on_embed_response.
    """

    class FakeUsage:
        prompt_tokens = None

    class FakeResponse:
        id = None
        model = None
        data = []
        usage = FakeUsage()

    client = MockEmbeddingsClient(response=FakeResponse())
    with logfire.instrument_azure_ai_inference(client):
        client.embed(model='text-embedding-ada-002', input=['Hi'])
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1


def test_no_messages_in_request(exporter: TestExporter) -> None:
    """Test chat completion with no messages."""
    client = MockChatCompletionsClient()
    with logfire.instrument_azure_ai_inference(client):
        client.complete(model='gpt-4', messages=[])
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert 'gen_ai.input.messages' not in spans[0]['attributes']


def test_system_message_non_string_content() -> None:
    """Test system message with non-string content.

    Exercises the false branch of isinstance(content, str) for system messages.
    """
    from logfire._internal.integrations.llm_providers.azure_ai_inference import convert_messages_to_semconv

    messages = [
        {'role': 'system', 'content': None},
        {'role': 'user', 'content': 'Hi'},
    ]
    input_msgs, system_instructions = convert_messages_to_semconv(messages)
    assert system_instructions == []
    assert len(input_msgs) == 1


def test_response_no_output_messages() -> None:
    """Test convert_response_to_semconv with empty choices.

    Exercises the false branch of `if output_messages:` in _on_chat_response.
    """
    from logfire._internal.integrations.llm_providers.azure_ai_inference import convert_response_to_semconv

    class EmptyResponse:
        choices = []

    output = convert_response_to_semconv(EmptyResponse())
    assert output == []


def test_response_tool_call_no_function() -> None:
    """Test response tool call without function attribute.

    Exercises the false branch of `if func:` in convert_response_to_semconv.
    """
    from logfire._internal.integrations.llm_providers.azure_ai_inference import convert_response_to_semconv

    class FakeToolCall:
        id = 'tc1'
        function = None

    class FakeMessage:
        role = 'assistant'
        content = None
        tool_calls = [FakeToolCall()]

    class FakeChoice:
        message = FakeMessage()
        finish_reason = None

    class FakeResponse:
        choices = [FakeChoice()]

    output = convert_response_to_semconv(FakeResponse())
    assert len(output) == 1
    assert output[0]['parts'] == []


def test_stream_wrapped_with_context_manager(exporter: TestExporter) -> None:
    """Test sync stream where wrapped object has __enter__/__exit__."""

    class ContextManagerIterator:
        def __init__(self, items: list[Any]) -> None:
            self.items = items
            self.entered = False
            self.exited = False

        def __enter__(self) -> ContextManagerIterator:
            self.entered = True
            return self

        def __exit__(self, *args: Any) -> None:
            self.exited = True

        def __iter__(self) -> Iterator[Any]:
            return iter(self.items)

    chunks = _make_streaming_chunks()
    wrapped = ContextManagerIterator(chunks)

    class MockChatCompletionsClientWithCM:
        __module__ = 'azure.ai.inference'

        def complete(self, **kwargs: Any) -> Any:
            if kwargs.get('stream'):
                return wrapped
            return _make_chat_response()

    client = MockChatCompletionsClientWithCM()
    with logfire.instrument_azure_ai_inference(client):
        response = client.complete(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Hi'}],
            stream=True,
        )
        with response:
            for _ in response:
                pass
    assert wrapped.entered
    assert wrapped.exited
    assert len(exporter.exported_spans_as_dict()) == 2


@pytest.mark.anyio
async def test_async_stream_wrapped_with_context_manager(exporter: TestExporter) -> None:
    """Test async stream where wrapped object has __aenter__/__aexit__."""

    class AsyncContextManagerIterator:
        def __init__(self, items: list[Any]) -> None:
            self.items = items
            self.entered = False
            self.exited = False

        async def __aenter__(self) -> AsyncContextManagerIterator:
            self.entered = True
            return self

        async def __aexit__(self, *args: Any) -> None:
            self.exited = True

        async def __aiter__(self) -> AsyncIterator[Any]:
            for item in self.items:
                yield item

    chunks = _make_streaming_chunks()
    wrapped = AsyncContextManagerIterator(chunks)

    class MockAsyncChatCompletionsClientWithCM:
        __module__ = 'azure.ai.inference.aio'

        async def complete(self, **kwargs: Any) -> Any:
            if kwargs.get('stream'):
                return wrapped
            return _make_chat_response()

    client = MockAsyncChatCompletionsClientWithCM()
    with logfire.instrument_azure_ai_inference(client):
        response = await client.complete(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Hi'}],
            stream=True,
        )
        async with response:
            async for _ in response:
                pass
    assert wrapped.entered
    assert wrapped.exited
    assert len(exporter.exported_spans_as_dict()) == 2


def test_streaming_empty_chunks(exporter: TestExporter) -> None:
    """Test streaming with chunks that have no choices or no content."""
    empty_chunks = [
        StreamingChatCompletionsUpdate(
            id='test-id',
            model='gpt-4',
            created=datetime(2024, 1, 1),
            choices=[],
        ),
        StreamingChatCompletionsUpdate(
            id='test-id',
            model='gpt-4',
            created=datetime(2024, 1, 1),
            choices=[StreamingChatChoiceUpdate(index=0, delta=None)],
        ),
        StreamingChatCompletionsUpdate(
            id='test-id',
            model='gpt-4',
            created=datetime(2024, 1, 1),
            choices=[StreamingChatChoiceUpdate(index=0, delta=StreamingChatResponseMessageUpdate(content=None))],
        ),
    ]
    client = MockChatCompletionsClient(stream_chunks=empty_chunks)
    with logfire.instrument_azure_ai_inference(client):
        response = client.complete(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Hi'}],
            stream=True,
        )
        list(response)
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    # Streaming info span should NOT have output messages (no actual content)
    assert 'gen_ai.output.messages' not in spans[1]['attributes']


@pytest.mark.anyio
async def test_async_streaming_empty_chunks(exporter: TestExporter) -> None:
    """Test async streaming with chunks that have no choices or no content."""
    empty_chunks = [
        StreamingChatCompletionsUpdate(
            id='test-id',
            model='gpt-4',
            created=datetime(2024, 1, 1),
            choices=[],
        ),
        StreamingChatCompletionsUpdate(
            id='test-id',
            model='gpt-4',
            created=datetime(2024, 1, 1),
            choices=[StreamingChatChoiceUpdate(index=0, delta=None)],
        ),
    ]
    client = MockAsyncChatCompletionsClient(stream_chunks=empty_chunks)
    with logfire.instrument_azure_ai_inference(client):
        response = await client.complete(
            messages=[{'role': 'user', 'content': 'Hi'}],
            stream=True,
        )
        async for _ in response:
            pass
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert 'gen_ai.output.messages' not in spans[1]['attributes']


def test_streaming_no_model_chunks(exporter: TestExporter) -> None:
    """Test streaming where both request and chunk have no model.

    Exercises false branch of `if model:` in _record_chunk (sync).
    """
    no_model_chunks = [
        StreamingChatCompletionsUpdate(
            id='test-id',
            model=None,
            created=datetime(2024, 1, 1),
            choices=[StreamingChatChoiceUpdate(index=0, delta=StreamingChatResponseMessageUpdate(content='Hi'))],
        ),
    ]
    client = MockChatCompletionsClient(stream_chunks=no_model_chunks)
    with logfire.instrument_azure_ai_inference(client):
        response = client.complete(
            messages=[{'role': 'user', 'content': 'Hi'}],
            stream=True,
        )
        list(response)
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 2


@pytest.mark.anyio
async def test_async_streaming_no_model_chunks(exporter: TestExporter) -> None:
    """Test async streaming where both request and chunk have no model.

    Exercises false branch of `if model:` in _record_chunk (async).
    """
    no_model_chunks = [
        StreamingChatCompletionsUpdate(
            id='test-id',
            model=None,
            created=datetime(2024, 1, 1),
            choices=[StreamingChatChoiceUpdate(index=0, delta=StreamingChatResponseMessageUpdate(content='Hi'))],
        ),
    ]
    client = MockAsyncChatCompletionsClient(stream_chunks=no_model_chunks)
    with logfire.instrument_azure_ai_inference(client):
        response = await client.complete(
            messages=[{'role': 'user', 'content': 'Hi'}],
            stream=True,
        )
        async for _ in response:
            pass
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 2


def test_message_conversion_with_typed_objects() -> None:
    """Test that Azure SDK typed message objects are converted correctly."""
    from azure.ai.inference.models import SystemMessage, UserMessage

    from logfire._internal.integrations.llm_providers.azure_ai_inference import convert_messages_to_semconv

    messages = [
        SystemMessage(content='You are helpful.'),
        UserMessage(content='Hello'),
    ]
    input_msgs, system_instructions = convert_messages_to_semconv(messages)
    assert system_instructions == [{'type': 'text', 'content': 'You are helpful.'}]
    assert input_msgs == [{'role': 'user', 'parts': [{'type': 'text', 'content': 'Hello'}]}]


def test_message_conversion_with_tool_messages() -> None:
    """Test that tool messages are converted correctly."""
    from logfire._internal.integrations.llm_providers.azure_ai_inference import convert_messages_to_semconv

    messages = [
        {'role': 'user', 'content': 'What is the weather?'},
        {
            'role': 'assistant',
            'content': '',
            'tool_calls': [
                {
                    'id': 'call_1',
                    'type': 'function',
                    'function': {'name': 'get_weather', 'arguments': '{"city": "London"}'},
                },
            ],
        },
        {'role': 'tool', 'content': '72F', 'tool_call_id': 'call_1'},
    ]
    input_msgs, system_instructions = convert_messages_to_semconv(messages)
    assert len(input_msgs) == 3
    assert system_instructions == []
    # User message
    assert input_msgs[0] == {'role': 'user', 'parts': [{'type': 'text', 'content': 'What is the weather?'}]}
    # Assistant with tool call
    assert input_msgs[1]['role'] == 'assistant'
    tool_part: Any = input_msgs[1]['parts'][0]
    assert tool_part['type'] == 'tool_call'
    assert tool_part['name'] == 'get_weather'
    # Tool response
    assert input_msgs[2]['role'] == 'tool'
    tool_resp: Any = input_msgs[2]['parts'][0]
    assert tool_resp['type'] == 'tool_call_response'
    assert tool_resp['id'] == 'call_1'
    assert tool_resp['response'] == '72F'
