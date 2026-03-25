from __future__ import annotations

import asyncio
from typing import Any

from logfire._internal.annotations_client import AnnotationsClient
from logfire._internal.config import GLOBAL_CONFIG, get_base_url_from_token


def _get_client() -> AnnotationsClient:
    """Get or create an AnnotationsClient from the global config."""
    token = GLOBAL_CONFIG.token
    if not token:
        raise ValueError('Logfire is not configured with a token. Call logfire.configure() first.')
    write_token = token[0] if isinstance(token, list) else token
    advanced = GLOBAL_CONFIG.advanced
    base_url = advanced.base_url if advanced and advanced.base_url else get_base_url_from_token(write_token)
    return AnnotationsClient(base_url=base_url, token=write_token)


async def create_annotation(
    *,
    trace_id: str,
    span_id: str,
    name: str,
    value: bool | int | float | str,
    annotation_type: str = 'feedback',
    comment: str | None = None,
    source: str = 'sdk',
    source_name: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Create an annotation on a span via the Logfire HTTP API.

    Args:
        trace_id: The trace ID (32-char hex string).
        span_id: The span ID (16-char hex string).
        name: The name of the annotation.
        value: The annotation value.
        annotation_type: The type of annotation (e.g., 'feedback', 'eval').
        comment: An optional comment or reason.
        source: The source of the annotation (e.g., 'sdk', 'online_eval').
        source_name: An optional name for the specific source.
        idempotency_key: Optional key for idempotent upserts.
        metadata: Optional metadata dict.
    """
    annotation: dict[str, Any] = {
        'trace_id': trace_id,
        'span_id': span_id,
        'name': name,
        'value': value,
        'annotation_type': annotation_type,
        'source': source,
    }
    if comment is not None:
        annotation['comment'] = comment
    if source_name is not None:
        annotation['source_name'] = source_name
    if idempotency_key is not None:
        annotation['idempotency_key'] = idempotency_key
    if metadata is not None:
        annotation['metadata'] = metadata

    client = _get_client()
    try:
        await client.create_annotations_batch([annotation])
    finally:
        await client.close()


def create_annotation_sync(
    *,
    trace_id: str,
    span_id: str,
    name: str,
    value: bool | int | float | str,
    annotation_type: str = 'feedback',
    comment: str | None = None,
    source: str = 'sdk',
    source_name: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Sync version of `create_annotation`.

    Args:
        trace_id: The trace ID (32-char hex string).
        span_id: The span ID (16-char hex string).
        name: The name of the annotation.
        value: The annotation value.
        annotation_type: The type of annotation (e.g., 'feedback', 'eval').
        comment: An optional comment or reason.
        source: The source of the annotation (e.g., 'sdk', 'online_eval').
        source_name: An optional name for the specific source.
        idempotency_key: Optional key for idempotent upserts.
        metadata: Optional metadata dict.
    """
    asyncio.run(
        create_annotation(
            trace_id=trace_id,
            span_id=span_id,
            name=name,
            value=value,
            annotation_type=annotation_type,
            comment=comment,
            source=source,
            source_name=source_name,
            idempotency_key=idempotency_key,
            metadata=metadata,
        )
    )
