"""HTTP client for the optimization control plane API."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from logfire._internal.config import get_base_url_from_token

try:
    from httpx import AsyncClient, Timeout
except ImportError as e:  # pragma: no cover
    raise ImportError('httpx is required for optimization. Install with: pip install httpx') from e


class OptimizationApiError(Exception):
    """Raised when the optimization API returns an error."""

    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f'Optimization API error {status_code}: {detail}')


class AsyncOptimizationClient:
    """Async HTTP client for the optimization control plane API.

    Communicates with the Logfire backend to create optimizations,
    request proposals, submit evaluations, and manage approvals.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url or get_base_url_from_token(api_key)
        self._client = AsyncClient(
            timeout=Timeout(timeout),
            base_url=self.base_url,
            headers={'authorization': f'Bearer {api_key}'},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncOptimizationClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def _handle_response(self, response: Any) -> Any:
        if response.status_code >= 400:
            try:
                detail = response.json().get('detail', response.text)
            except Exception:
                detail = response.text
            raise OptimizationApiError(response.status_code, detail)
        if response.status_code == 204:
            return None
        return response.json()

    # --- Optimization endpoints ---

    async def create_optimization(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new optimization."""
        response = await self._client.post('/v1/optimizations/', json=data)
        return self._handle_response(response)

    async def get_optimization(self, optimization_id: str) -> dict[str, Any]:
        """Get an optimization by ID."""
        response = await self._client.get(f'/v1/optimizations/{optimization_id}/')
        return self._handle_response(response)

    async def get_optimization_by_variable_name(self, variable_name: str) -> dict[str, Any] | None:
        """Get an optimization by variable name. Returns None if not found."""
        response = await self._client.get(f'/v1/optimizations/by-variable/{variable_name}/')
        if response.status_code == 404:
            return None
        return self._handle_response(response)

    # --- Iteration endpoints ---

    async def request_proposal(
        self,
        optimization_id: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Request a new proposal from the optimization agent.

        Args:
            optimization_id: The optimization ID.
            context: Optional evaluation context to pass to the worker agent.
                     Stored as trigger_data on the iteration record.
        """
        data: dict[str, Any] | None = None
        if context:
            data = {'trigger_data': {'evaluation_context': context}}
        response = await self._client.post(
            f'/v1/optimizations/{optimization_id}/actions/request-proposal',
            json=data,
        )
        return self._handle_response(response)

    async def get_iteration(self, optimization_id: str, iteration_id: str) -> dict[str, Any]:
        """Get an iteration by ID."""
        response = await self._client.get(f'/v1/optimizations/{optimization_id}/iterations/{iteration_id}/')
        return self._handle_response(response)

    async def list_iterations(self, optimization_id: str) -> list[dict[str, Any]]:
        """List iterations for an optimization."""
        response = await self._client.get(f'/v1/optimizations/{optimization_id}/iterations/')
        return self._handle_response(response)

    async def poll_iteration(
        self,
        optimization_id: str,
        iteration_id: str,
        target_status: set[str],
        timeout: float = 300.0,
        poll_interval: float = 2.0,
    ) -> dict[str, Any]:
        """Poll an iteration until it reaches one of the target statuses.

        Args:
            optimization_id: The optimization ID.
            iteration_id: The iteration ID to poll.
            target_status: Set of statuses to wait for.
            timeout: Maximum time to wait in seconds (default 5 minutes).
            poll_interval: Time between polls in seconds.

        Returns:
            The iteration data once it reaches a target status.

        Raises:
            TimeoutError: If the iteration doesn't reach a target status in time.
        """
        deadline = time.monotonic() + timeout
        last_status: str | None = None
        while time.monotonic() < deadline:
            iteration = await self.get_iteration(optimization_id, iteration_id)
            last_status = iteration['status']
            if last_status in target_status:
                return iteration
            await asyncio.sleep(poll_interval)
        raise TimeoutError(
            f'Iteration {iteration_id} did not reach status {target_status} '
            f'within {timeout}s (last status: {last_status})'
        )

    async def submit_evaluation(
        self,
        optimization_id: str,
        iteration_id: str,
        control_metrics: dict[str, float] | None = None,
        treatment_metrics: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Submit evaluation results for an iteration."""
        data: dict[str, Any] = {}
        if control_metrics is not None:
            data['control_metrics'] = control_metrics
        if treatment_metrics is not None:
            data['treatment_metrics'] = treatment_metrics
        response = await self._client.post(
            f'/v1/optimizations/{optimization_id}/iterations/{iteration_id}/evaluation',
            json=data,
        )
        return self._handle_response(response)

    # --- Action endpoints ---

    async def approve(self, optimization_id: str) -> dict[str, Any]:
        """Approve the current proposal."""
        response = await self._client.post(f'/v1/optimizations/{optimization_id}/actions/approve')
        return self._handle_response(response)

    async def reject(self, optimization_id: str, reason: str | None = None) -> dict[str, Any]:
        """Reject the current proposal."""
        data = {'reason': reason} if reason else {}
        response = await self._client.post(
            f'/v1/optimizations/{optimization_id}/actions/reject',
            json=data,
        )
        return self._handle_response(response)

    async def cancel(self, optimization_id: str) -> dict[str, Any]:
        """Cancel the active iteration."""
        response = await self._client.post(f'/v1/optimizations/{optimization_id}/actions/cancel')
        return self._handle_response(response)

    async def delete_optimization(self, optimization_id: str) -> None:
        """Delete an optimization."""
        response = await self._client.delete(f'/v1/optimizations/{optimization_id}/')
        if response.status_code >= 400:
            self._handle_response(response)
