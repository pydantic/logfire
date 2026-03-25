from collections.abc import Sequence
from typing import Any

from logfire._internal.annotations_client import AnnotationsClient

class LogfireSink:
    """Sends pydantic-evals online evaluation results to Logfire as annotations."""
    def __init__(self, client: AnnotationsClient) -> None: ...
    async def submit(
        self,
        *,
        results: Sequence[Any],
        failures: Sequence[Any],
        context: Any,
        span_reference: Any | None,
    ) -> None: ...
