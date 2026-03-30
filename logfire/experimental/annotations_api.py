from __future__ import annotations

from typing import Any

from logfire._internal.config import GLOBAL_CONFIG, get_base_url_from_token
from logfire.experimental.api_client import AsyncLogfireAPIClient, LogfireAPIClient


def _get_api_key_and_base_url() -> tuple[str, str]:
    """Get API key and base URL from the global config."""
    api_key = GLOBAL_CONFIG.api_key
    if not api_key:
        raise ValueError(
            'Logfire is not configured with an API key. '
            'Set the LOGFIRE_API_KEY environment variable or pass api_key to logfire.configure().'
        )
    advanced = GLOBAL_CONFIG.advanced
    base_url = advanced.base_url if advanced and advanced.base_url else get_base_url_from_token(api_key)
    return api_key, base_url


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
    api_key, base_url = _get_api_key_and_base_url()
    async with AsyncLogfireAPIClient(api_key=api_key, base_url=base_url) as client:
        await client.create_annotations([body])


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
    api_key, base_url = _get_api_key_and_base_url()
    with LogfireAPIClient(api_key=api_key, base_url=base_url) as client:
        client.create_annotations([body])
