from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

import logfire
from logfire._internal.annotations_client import AnnotationsClient


def _idempotency_key(trace_id: str, span_id: str, source_name: str, name: str) -> str:
    """Compute a deterministic idempotency key for an annotation."""
    payload = f'{trace_id}:{span_id}:{source_name}:{name}'
    return hashlib.sha256(payload.encode()).hexdigest()


def _serialize_value(value: bool | int | float | str) -> Any:
    """Serialize an evaluation result value for the annotations API."""
    if isinstance(value, bool):
        return {'type': 'assertion', 'value': value}
    if isinstance(value, (int, float)):
        return {'type': 'score', 'value': value}
    return {'type': 'label', 'value': value}


class LogfireSink:
    """Sends pydantic-evals online evaluation results to Logfire as annotations.

    Implements the `pydantic_evals.online.EvaluationSink` protocol structurally
    (no import of pydantic-evals at module level).
    """

    def __init__(self, client: AnnotationsClient) -> None:
        self._client = client

    async def submit(
        self,
        *,
        results: Sequence[Any],
        failures: Sequence[Any],
        context: Any,
        span_reference: Any | None,
    ) -> None:
        """Submit evaluation results and failures as annotations to Logfire.

        Args:
            results: Sequence of `pydantic_evals.evaluators.evaluator.EvaluationResult`.
            failures: Sequence of `pydantic_evals.evaluators.evaluator.EvaluatorFailure`.
            context: A `pydantic_evals.evaluators.context.EvaluatorContext`.
            span_reference: A `pydantic_evals.online.SpanReference` or None.
        """
        if span_reference is None:
            return

        trace_id: str = span_reference.trace_id
        span_id: str = span_reference.span_id
        annotations: list[dict[str, Any]] = []

        for result in results:
            source_name: str = f'{result.source.name}:{result.name}'
            annotation: dict[str, Any] = {
                'trace_id': trace_id,
                'span_id': span_id,
                'annotation_type': 'eval',
                'name': result.name,
                'value': _serialize_value(result.value),
                'source': 'online_eval',
                'source_name': source_name,
                'idempotency_key': _idempotency_key(trace_id, span_id, source_name, result.name),
            }
            if result.reason is not None:
                annotation['comment'] = result.reason
            if context.metadata is not None:
                annotation['metadata'] = context.metadata
            annotations.append(annotation)

        for failure in failures:
            source_name = f'{failure.source.name}:{failure.name}'
            annotation = {
                'trace_id': trace_id,
                'span_id': span_id,
                'annotation_type': 'eval',
                'name': failure.name,
                'value': json.dumps({'error': True, 'error_message': failure.error_message}),
                'source': 'online_eval',
                'source_name': source_name,
                'idempotency_key': _idempotency_key(trace_id, span_id, source_name, failure.name),
            }
            if failure.error_stacktrace:
                annotation['comment'] = failure.error_stacktrace[:1000]
            if context.metadata is not None:
                annotation['metadata'] = context.metadata
            annotations.append(annotation)

        if not annotations:
            return

        try:
            await self._client.create_annotations_batch(annotations)
        except Exception as exc:
            logfire.warn('LogfireSink submit failed: {error}', error=str(exc))
