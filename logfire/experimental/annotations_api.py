from __future__ import annotations

from typing import Any

import httpx

from logfire._internal.annotations_client import DEFAULT_TIMEOUT, AnnotationsClient
from logfire._internal.config import GLOBAL_CONFIG, get_base_url_from_token


def _get_token_and_base_url() -> tuple[str, str]:
    """Get write token and base URL from the global config."""
    token = GLOBAL_CONFIG.token
    if not token:
        raise ValueError('Logfire is not configured with a token. Call logfire.configure() first.')
    write_token = token[0] if isinstance(token, list) else token
    advanced = GLOBAL_CONFIG.advanced
    base_url = advanced.base_url if advanced and advanced.base_url else get_base_url_from_token(write_token)
    return write_token, base_url


def _build_annotation_body(
    *,
    trace_id: str,
    span_id: str,
    name: str,
    value: bool | int | float | str,
    comment: str | None = None,
    source: str = 'app',
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the annotation request body in the platform V1 API format."""
    annotation_value: Any = value
    if comment is not None:
        annotation_value = {'value': value, 'reason': comment}

    body: dict[str, Any] = {
        'trace_id': trace_id,
        'span_id': span_id,
        'values': {name: annotation_value},
        'source': source,
    }
    if metadata is not None:
        body['metadata'] = metadata
    return body


async def create_annotation(
    *,
    trace_id: str,
    span_id: str,
    name: str,
    value: bool | int | float | str,
    comment: str | None = None,
    source: str = 'app',
    metadata: dict[str, Any] | None = None,
) -> None:
    """Create an annotation on a span via the Logfire HTTP API.

    Args:
        trace_id: The trace ID (32-char hex string).
        span_id: The span ID (16-char hex string).
        name: The name of the annotation (score dimension).
        value: The annotation value (bool, int, float, or str).
        comment: An optional comment or reason.
        source: The source of the annotation ('app' or 'automated').
        metadata: Optional metadata dict.
    """
    body = _build_annotation_body(
        trace_id=trace_id,
        span_id=span_id,
        name=name,
        value=value,
        comment=comment,
        source=source,
        metadata=metadata,
    )
    write_token, base_url = _get_token_and_base_url()
    client = AnnotationsClient(base_url=base_url, token=write_token)
    try:
        await client.create_annotations_batch([body])
    finally:
        await client.close()


def create_annotation_sync(
    *,
    trace_id: str,
    span_id: str,
    name: str,
    value: bool | int | float | str,
    comment: str | None = None,
    source: str = 'app',
    metadata: dict[str, Any] | None = None,
) -> None:
    """Sync version of `create_annotation`.

    Safe to call from both sync contexts and within running event loops.

    Args:
        trace_id: The trace ID (32-char hex string).
        span_id: The span ID (16-char hex string).
        name: The name of the annotation (score dimension).
        value: The annotation value (bool, int, float, or str).
        comment: An optional comment or reason.
        source: The source of the annotation ('app' or 'automated').
        metadata: Optional metadata dict.
    """
    body = _build_annotation_body(
        trace_id=trace_id,
        span_id=span_id,
        name=name,
        value=value,
        comment=comment,
        source=source,
        metadata=metadata,
    )
    write_token, base_url = _get_token_and_base_url()
    with httpx.Client(
        base_url=base_url,
        headers={'Authorization': write_token},
        timeout=DEFAULT_TIMEOUT,
    ) as client:
        response = client.post('/v1/annotations', json={'annotations': [body]})
        response.raise_for_status()
