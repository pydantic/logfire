from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import httpx

import logfire
from logfire.experimental.api_client import AsyncLogfireAPIClient


class LogfireSink:
    """Sends pydantic-evals online evaluation results to Logfire as annotations.

    Implements the `pydantic_evals.online.EvaluationSink` protocol structurally
    (no import of pydantic-evals at module level).
    """

    def __init__(self, client: AsyncLogfireAPIClient) -> None:
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
        values: dict[str, Any] = {}

        for result in results:
            value: Any = result.value
            if result.reason is not None:
                value = {'value': value, 'reason': result.reason}
            values[result.name] = value

        for failure in failures:
            error_value = json.dumps({'error': True, 'error_message': failure.error_message})
            if failure.error_stacktrace:
                values[failure.name] = {'value': error_value, 'reason': failure.error_stacktrace[:1000]}
            else:
                values[failure.name] = error_value

        if not values:
            return

        annotation: dict[str, Any] = {
            'trace_id': trace_id,
            'span_id': span_id,
            'values': values,
            'source': 'automated',
        }
        if context.metadata is not None:
            annotation['metadata'] = context.metadata

        try:
            await self._client.create_annotations([annotation])
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                try:
                    await self._client.create_annotations([annotation])
                except Exception as retry_exc:
                    logfire.error('Annotations batch retry failed: {error}', error=str(retry_exc), _exc_info=retry_exc)
            else:
                logfire.error(
                    'Annotations batch request failed: {status} {error}',
                    status=exc.response.status_code,
                    error=str(exc),
                )
        except httpx.TimeoutException:
            try:
                await self._client.create_annotations([annotation])
            except Exception as retry_exc:
                logfire.error('Annotations batch retry after timeout failed: {error}', error=str(retry_exc))
        except Exception as exc:
            logfire.error('LogfireSink submit failed: {error}', error=str(exc))
