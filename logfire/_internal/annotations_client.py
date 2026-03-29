from __future__ import annotations

from typing import Any

import httpx

import logfire

DEFAULT_TIMEOUT = httpx.Timeout(30.0)


class AnnotationsClient:
    """Async HTTP client for the Logfire annotations API.

    Uses write tokens (same as ingest) for authentication.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            headers={'Authorization': token},
            timeout=timeout,
        )

    async def create_annotations_batch(self, annotations: list[dict[str, Any]]) -> None:
        """POST /v1/annotations with a batch of annotations."""
        try:
            response = await self._client.post('/v1/annotations', json={'annotations': annotations})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                # Single retry on 5xx
                try:
                    response = await self._client.post('/v1/annotations', json={'annotations': annotations})
                    response.raise_for_status()
                except Exception as retry_exc:
                    logfire.error('Annotations batch retry failed: {error}', _exc_info=retry_exc)
            else:
                logfire.error(
                    'Annotations batch request failed: {status} {error}',
                    status=exc.response.status_code,
                    error=str(exc),
                )
        except httpx.TimeoutException:
            # Single retry on timeout
            try:
                response = await self._client.post('/v1/annotations', json={'annotations': annotations})
                response.raise_for_status()
            except Exception as retry_exc:
                logfire.error('Annotations batch retry after timeout failed: {error}', error=str(retry_exc))
        except Exception as exc:
            logfire.error('Annotations batch request failed: {error}', error=str(exc))

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
