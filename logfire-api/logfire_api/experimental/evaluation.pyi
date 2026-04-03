from collections.abc import Sequence
from typing import Any

from logfire.experimental.api_client import AsyncLogfireAPIClient

class LogfireSink:
    """Sends pydantic-evals online evaluation results to Logfire as annotations."""
    def __init__(self, client: AsyncLogfireAPIClient) -> None: ...
    async def submit(
        self,
        *,
        results: Sequence[Any],
        failures: Sequence[Any],
        context: Any,
        span_reference: Any | None,
    ) -> None: ...
