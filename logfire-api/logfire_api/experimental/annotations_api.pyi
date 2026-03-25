from typing import Any

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
    """Create an annotation on a span via the Logfire HTTP API."""
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
    """Sync version of `create_annotation`."""
