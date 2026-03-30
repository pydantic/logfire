from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest
from inline_snapshot import snapshot

from logfire._internal.annotations_client import AnnotationsClient
from logfire.experimental.evaluation import LogfireSink


@dataclass
class FakeSource:
    name: str
    arguments: None = None


@dataclass
class FakeResult:
    name: str
    value: bool | int | float | str
    reason: str | None
    source: FakeSource


@dataclass
class FakeFailure:
    name: str
    error_message: str
    error_stacktrace: str
    source: FakeSource


@dataclass
class FakeSpanReference:
    trace_id: str
    span_id: str


@dataclass
class FakeContext:
    name: str | None = None
    inputs: Any = None
    output: Any = None
    expected_output: Any = None
    metadata: Any = None
    duration: float = 0.0
    attributes: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None


@pytest.mark.anyio
async def test_submit_results() -> None:
    """Results are correctly mapped to annotation payloads."""
    mock_client = AsyncMock(spec=AnnotationsClient)
    sink = LogfireSink(client=mock_client)

    results = [
        FakeResult(name='helpfulness', value=True, reason='Very helpful', source=FakeSource(name='LLMJudge')),
        FakeResult(name='score', value=0.9, reason=None, source=FakeSource(name='Scorer')),
    ]

    await sink.submit(
        results=results,
        failures=[],
        context=FakeContext(metadata={'model': 'gpt-4'}),
        span_reference=FakeSpanReference(trace_id='a' * 32, span_id='b' * 16),
    )

    mock_client.create_annotations_batch.assert_called_once()
    annotations = mock_client.create_annotations_batch.call_args[0][0]
    assert len(annotations) == 1

    assert annotations[0] == snapshot(
        {
            'trace_id': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            'span_id': 'bbbbbbbbbbbbbbbb',
            'values': {
                'helpfulness': {'value': True, 'reason': 'Very helpful'},
                'score': 0.9,
            },
            'source': 'automated',
            'metadata': {'model': 'gpt-4'},
        }
    )


@pytest.mark.anyio
async def test_submit_failures() -> None:
    """Failures are correctly mapped to annotation payloads."""
    mock_client = AsyncMock(spec=AnnotationsClient)
    sink = LogfireSink(client=mock_client)

    failures = [
        FakeFailure(
            name='broken_eval',
            error_message='KeyError: missing_key',
            error_stacktrace='Traceback...\nKeyError: missing_key',
            source=FakeSource(name='BrokenEval'),
        ),
    ]

    await sink.submit(
        results=[],
        failures=failures,
        context=FakeContext(),
        span_reference=FakeSpanReference(trace_id='a' * 32, span_id='b' * 16),
    )

    mock_client.create_annotations_batch.assert_called_once()
    annotations = mock_client.create_annotations_batch.call_args[0][0]
    assert len(annotations) == 1
    failure_value = annotations[0]['values']['broken_eval']
    assert failure_value['reason'] == 'Traceback...\nKeyError: missing_key'
    assert '"error": true' in failure_value['value']


@pytest.mark.anyio
async def test_submit_none_span_reference_is_noop() -> None:
    """When span_reference is None, nothing is sent."""
    mock_client = AsyncMock(spec=AnnotationsClient)
    sink = LogfireSink(client=mock_client)

    await sink.submit(
        results=[FakeResult(name='test', value=True, reason=None, source=FakeSource(name='Test'))],
        failures=[],
        context=FakeContext(),
        span_reference=None,
    )

    mock_client.create_annotations_batch.assert_not_called()


@pytest.mark.anyio
async def test_submit_empty_results_and_failures_is_noop() -> None:
    """When there are no results or failures, nothing is sent."""
    mock_client = AsyncMock(spec=AnnotationsClient)
    sink = LogfireSink(client=mock_client)

    await sink.submit(
        results=[],
        failures=[],
        context=FakeContext(),
        span_reference=FakeSpanReference(trace_id='a' * 32, span_id='b' * 16),
    )

    mock_client.create_annotations_batch.assert_not_called()


@pytest.mark.anyio
async def test_submit_catches_exceptions() -> None:
    """Exceptions from the client are caught and logged, not raised."""
    mock_client = AsyncMock(spec=AnnotationsClient)
    mock_client.create_annotations_batch.side_effect = RuntimeError('connection failed')
    sink = LogfireSink(client=mock_client)

    # Should not raise
    await sink.submit(
        results=[FakeResult(name='test', value=True, reason=None, source=FakeSource(name='Test'))],
        failures=[],
        context=FakeContext(),
        span_reference=FakeSpanReference(trace_id='a' * 32, span_id='b' * 16),
    )


@pytest.mark.anyio
async def test_submit_failure_without_stacktrace() -> None:
    """Failures without stacktrace don't include reason in value."""
    mock_client = AsyncMock(spec=AnnotationsClient)
    sink = LogfireSink(client=mock_client)

    failures = [
        FakeFailure(
            name='broken_eval',
            error_message='KeyError: missing_key',
            error_stacktrace='',
            source=FakeSource(name='BrokenEval'),
        ),
    ]

    await sink.submit(
        results=[],
        failures=failures,
        context=FakeContext(),
        span_reference=FakeSpanReference(trace_id='a' * 32, span_id='b' * 16),
    )

    mock_client.create_annotations_batch.assert_called_once()
    annotations = mock_client.create_annotations_batch.call_args[0][0]
    failure_value = annotations[0]['values']['broken_eval']
    # When no stacktrace, value is a bare string (no reason dict)
    assert isinstance(failure_value, str)
    assert '"error": true' in failure_value
