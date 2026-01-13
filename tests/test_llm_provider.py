"""Tests for context preservation during streaming in llm_provider."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import Mock

import pytest
from opentelemetry import trace

import logfire
from logfire._internal.integrations.llm_providers.llm_provider import (
    instrument_llm_provider,
    record_streaming,
)
from logfire._internal.integrations.llm_providers.semconv import PROVIDER_NAME
from logfire._internal.integrations.llm_providers.types import EndpointConfig, StreamState
from logfire.propagate import get_context
from logfire.testing import TestExporter


class MockStreamState(StreamState):
    def __init__(self):
        self.chunks: list[str] = []

    def record_chunk(self, chunk: Any) -> None:
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
        stream_cls = kwargs.get('stream_cls', MockSyncStream)
        return stream_cls(self._chunks)


class MockAsyncClient:
    _is_instrumented_by_logfire = False

    def __init__(self, chunks: list[str] | None = None):
        self._chunks = chunks or []

    async def request(self, *args: Any, **kwargs: Any) -> Any:
        stream_cls = kwargs.get('stream_cls', MockAsyncStream)
        return stream_cls(self._chunks)


def get_endpoint_config(options: MockOptions) -> EndpointConfig:
    return EndpointConfig(
        message_template='Test with {request_data[model]!r}',
        span_data={'request_data': options.json_data},
        stream_state_cls=MockStreamState,
    )


on_response = Mock()


def is_async_client(client_type: type) -> bool:
    return issubclass(client_type, MockAsyncClient)


def test_record_streaming_preserves_context(exporter: TestExporter) -> None:
    with logfire.span('parent'):
        original_context = get_context()
        span_context = trace.get_current_span().get_span_context()
        expected_trace_id = span_context.trace_id
        expected_span_id = span_context.span_id

    # Outside the parent span, streaming log should still link to parent via attach_context
    with record_streaming(
        logfire.DEFAULT_LOGFIRE_INSTANCE,
        {'request_data': {'model': 'test-model'}},
        MockStreamState,
        original_context,
    ) as record_chunk:
        record_chunk('chunk')

    spans = exporter.exported_spans_as_dict()
    streaming = next(s for s in spans if 'streaming response' in s['name'])

    assert streaming['context']['trace_id'] == expected_trace_id
    assert streaming['parent']['span_id'] == expected_span_id


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
        span_context = trace.get_current_span().get_span_context()
        expected_trace_id = span_context.trace_id
        expected_span_id = span_context.span_id
        result = client.request(options=MockOptions(), stream=True, stream_cls=MockSyncStream)
        for _ in result.__stream__():
            pass

    spans = exporter.exported_spans_as_dict()
    request = next(s for s in spans if 'Test with' in s['name'])
    streaming = next(s for s in spans if 'streaming response' in s['name'])

    assert request['context']['trace_id'] == expected_trace_id
    assert streaming['context']['trace_id'] == expected_trace_id
    assert request['parent']['span_id'] == expected_span_id
    assert streaming['parent']['span_id'] == expected_span_id


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
        span_context = trace.get_current_span().get_span_context()
        expected_trace_id = span_context.trace_id
        expected_span_id = span_context.span_id
        result = await client.request(options=MockOptions(), stream=True, stream_cls=MockAsyncStream)
        async for _ in result.__stream__():
            pass

    spans = exporter.exported_spans_as_dict()
    request = next(s for s in spans if 'Test with' in s['name'])
    streaming = next(s for s in spans if 'streaming response' in s['name'])

    assert request['context']['trace_id'] == expected_trace_id
    assert streaming['context']['trace_id'] == expected_trace_id
    assert request['parent']['span_id'] == expected_span_id
    assert streaming['parent']['span_id'] == expected_span_id


@pytest.mark.parametrize(
    ('override_provider', 'expected_gen_ai_system'),
    [
        pytest.param('openrouter', 'openrouter', id='sets_custom_provider'),
        pytest.param(None, None, id='none_does_not_set_attribute'),
    ],
)
def test_override_provider_sync(
    exporter: TestExporter, override_provider: str | None, expected_gen_ai_system: str | None
) -> None:
    """Test that override_provider parameter controls the gen_ai.system and gen_ai.provider.name attributes for sync clients."""
    client = MockSyncClient()
    instrument_llm_provider(
        logfire=logfire.DEFAULT_LOGFIRE_INSTANCE,
        client=client,
        suppress_otel=False,
        scope_suffix='test',
        get_endpoint_config_fn=get_endpoint_config,
        on_response_fn=on_response,
        is_async_client_fn=is_async_client,
        override_provider=override_provider,
    )

    client.request(options=MockOptions())

    spans = exporter.exported_spans_as_dict()
    request = next(s for s in spans if 'Test with' in s['name'])

    if expected_gen_ai_system is None:
        # When override_provider is None, gen_ai.system should not be set by instrument_llm_provider
        # (it would be set later by on_response for OpenAI)
        assert 'gen_ai.system' not in request['attributes']
        assert PROVIDER_NAME not in request['attributes']
    else:
        assert request['attributes']['gen_ai.system'] == expected_gen_ai_system
        assert request['attributes'][PROVIDER_NAME] == expected_gen_ai_system


@pytest.mark.parametrize(
    ('override_provider', 'expected_gen_ai_system'),
    [
        pytest.param('openrouter', 'openrouter', id='sets_custom_provider'),
        pytest.param(None, None, id='none_does_not_set_attribute'),
    ],
)
async def test_override_provider_async(
    exporter: TestExporter, override_provider: str | None, expected_gen_ai_system: str | None
) -> None:
    """Test that override_provider parameter controls the gen_ai.system and gen_ai.provider.name attributes for async clients."""
    client = MockAsyncClient()
    instrument_llm_provider(
        logfire=logfire.DEFAULT_LOGFIRE_INSTANCE,
        client=client,
        suppress_otel=False,
        scope_suffix='test',
        get_endpoint_config_fn=get_endpoint_config,
        on_response_fn=on_response,
        is_async_client_fn=is_async_client,
        override_provider=override_provider,
    )

    await client.request(options=MockOptions())

    spans = exporter.exported_spans_as_dict()
    request = next(s for s in spans if 'Test with' in s['name'])

    if expected_gen_ai_system is None:
        assert 'gen_ai.system' not in request['attributes']
        assert PROVIDER_NAME not in request['attributes']
    else:
        assert request['attributes']['gen_ai.system'] == expected_gen_ai_system
        assert request['attributes'][PROVIDER_NAME] == expected_gen_ai_system
