"""Tests for context preservation during streaming in llm_provider."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

import logfire
from logfire._internal.integrations.llm_providers.llm_provider import (
    instrument_llm_provider,
    record_streaming,
)
from logfire._internal.integrations.llm_providers.types import EndpointConfig, StreamState
from logfire.propagate import get_context
from logfire.testing import TestExporter


class MockStreamState(StreamState):
    def __init__(self):
        self.chunks: list[str] = []

    def record_chunk(self, chunk: Any) -> None:
        if isinstance(chunk, str):
            self.chunks.append(chunk)

    def get_response_data(self) -> Any:
        return {'combined_chunk_content': ''.join(self.chunks), 'chunk_count': len(self.chunks)}


@dataclass
class MockOptions:
    """Simulates FinalRequestOptions from openai/anthropic clients."""

    url: str = '/test'
    json_data: dict[str, Any] = field(default_factory=lambda: {'model': 'test-model'})


class MockSyncStream:
    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    def __stream__(self) -> Iterator[str]:
        yield from self._chunks


class MockAsyncStream:
    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    async def __stream__(self) -> AsyncIterator[str]:
        for chunk in self._chunks:
            yield chunk


class MockSyncClient:
    _is_instrumented_by_logfire = False

    def __init__(self, chunks: list[str] | None = None):
        self._chunks = chunks or []

    def request(self, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get('stream') and self._chunks:
            stream_cls = kwargs.get('stream_cls', MockSyncStream)
            return stream_cls(self._chunks)
        return {'result': 'success'}


class MockAsyncClient:
    _is_instrumented_by_logfire = False

    def __init__(self, chunks: list[str] | None = None):
        self._chunks = chunks or []

    async def request(self, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get('stream') and self._chunks:
            stream_cls = kwargs.get('stream_cls', MockAsyncStream)
            return stream_cls(self._chunks)
        return {'result': 'success'}


def get_endpoint_config(options: MockOptions) -> EndpointConfig:
    return EndpointConfig(
        message_template='Test with {request_data[model]!r}',
        span_data={'request_data': options.json_data},
        stream_state_cls=MockStreamState,
    )


def on_response(response: Any, span: logfire.LogfireSpan) -> Any:
    return response


def is_async_client(client_type: type) -> bool:
    return issubclass(client_type, MockAsyncClient)


def test_record_streaming_preserves_context(exporter: TestExporter) -> None:
    with logfire.span('parent'):
        original_context = get_context()

    # Outside the parent span, streaming log should still link to parent via attach_context
    with record_streaming(
        logfire.DEFAULT_LOGFIRE_INSTANCE,
        {'request_data': {'model': 'test-model'}},
        MockStreamState,
        original_context,
    ) as record_chunk:
        record_chunk('chunk')

    spans = exporter.exported_spans_as_dict()
    parent = next(s for s in spans if s['name'] == 'parent')
    streaming = next(s for s in spans if 'streaming response' in s['name'])

    assert streaming['context']['trace_id'] == parent['context']['trace_id']
    assert streaming['parent']['span_id'] == parent['context']['span_id']


def test_sync_streaming_preserves_original_context(exporter: TestExporter) -> None:
    """Context captured before request span opens, so streaming and request spans are siblings."""
    client = MockSyncClient(chunks=['chunk1', 'chunk2'])
    instrument_llm_provider(
        logfire=logfire.DEFAULT_LOGFIRE_INSTANCE,
        client=client,
        suppress_otel=False,
        scope_suffix='test',
        get_endpoint_config_fn=get_endpoint_config,
        on_response_fn=on_response,
        is_async_client_fn=is_async_client,
    )

    with logfire.span('parent'):
        result = client.request(options=MockOptions(), stream=True, stream_cls=MockSyncStream)
        for _ in result.__stream__():
            pass

    spans = exporter.exported_spans_as_dict()
    parent = next(s for s in spans if s['name'] == 'parent')
    request = next(s for s in spans if 'Test with' in s['name'])
    streaming = next(s for s in spans if 'streaming response' in s['name'])

    assert request['context']['trace_id'] == parent['context']['trace_id']
    assert streaming['context']['trace_id'] == parent['context']['trace_id']
    assert request['parent']['span_id'] == parent['context']['span_id']
    assert streaming['parent']['span_id'] == parent['context']['span_id']


async def test_async_streaming_preserves_original_context(exporter: TestExporter) -> None:
    """Context captured before request span opens, so streaming and request spans are siblings."""
    client = MockAsyncClient(chunks=['chunk1', 'chunk2'])
    instrument_llm_provider(
        logfire=logfire.DEFAULT_LOGFIRE_INSTANCE,
        client=client,
        suppress_otel=False,
        scope_suffix='test',
        get_endpoint_config_fn=get_endpoint_config,
        on_response_fn=on_response,
        is_async_client_fn=is_async_client,
    )

    with logfire.span('parent'):
        result = await client.request(options=MockOptions(), stream=True, stream_cls=MockAsyncStream)
        async for _ in result.__stream__():
            pass

    spans = exporter.exported_spans_as_dict()
    parent = next(s for s in spans if s['name'] == 'parent')
    request = next(s for s in spans if 'Test with' in s['name'])
    streaming = next(s for s in spans if 'streaming response' in s['name'])

    assert request['context']['trace_id'] == parent['context']['trace_id']
    assert streaming['context']['trace_id'] == parent['context']['trace_id']
    assert request['parent']['span_id'] == parent['context']['span_id']
    assert streaming['parent']['span_id'] == parent['context']['span_id']
