from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from logfire.experimental.annotations_api import create_annotation


@pytest.mark.anyio
async def test_create_annotation_builds_correct_payload() -> None:
    """create_annotation sends the correct annotation payload."""
    mock_client = AsyncMock()
    mock_client.create_annotations_batch = AsyncMock()
    mock_client.close = AsyncMock()

    with patch('logfire.experimental.annotations_api._get_client', return_value=mock_client):
        await create_annotation(
            trace_id='a' * 32,
            span_id='b' * 16,
            name='quality',
            value=0.95,
            annotation_type='feedback',
            comment='Great response',
            source='sdk',
            source_name='manual',
            idempotency_key='key123',
            metadata={'reviewer': 'alice'},
        )

    mock_client.create_annotations_batch.assert_called_once()
    annotations = mock_client.create_annotations_batch.call_args[0][0]
    assert len(annotations) == 1
    assert annotations[0]['trace_id'] == 'a' * 32
    assert annotations[0]['span_id'] == 'b' * 16
    assert annotations[0]['name'] == 'quality'
    assert annotations[0]['value'] == 0.95
    assert annotations[0]['annotation_type'] == 'feedback'
    assert annotations[0]['comment'] == 'Great response'
    assert annotations[0]['source'] == 'sdk'
    assert annotations[0]['source_name'] == 'manual'
    assert annotations[0]['idempotency_key'] == 'key123'
    assert annotations[0]['metadata'] == {'reviewer': 'alice'}
    mock_client.close.assert_called_once()


@pytest.mark.anyio
async def test_create_annotation_minimal_payload() -> None:
    """Only required fields are included when optional args are not provided."""
    mock_client = AsyncMock()
    mock_client.create_annotations_batch = AsyncMock()
    mock_client.close = AsyncMock()

    with patch('logfire.experimental.annotations_api._get_client', return_value=mock_client):
        await create_annotation(
            trace_id='a' * 32,
            span_id='b' * 16,
            name='thumbs_up',
            value=True,
        )

    annotations = mock_client.create_annotations_batch.call_args[0][0]
    assert len(annotations) == 1
    assert 'comment' not in annotations[0]
    assert 'source_name' not in annotations[0]
    assert 'idempotency_key' not in annotations[0]
    assert 'metadata' not in annotations[0]
    assert annotations[0]['annotation_type'] == 'feedback'
    assert annotations[0]['source'] == 'sdk'
