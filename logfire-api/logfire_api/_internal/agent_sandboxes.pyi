from collections.abc import AsyncGenerator, Callable, Mapping as Mapping
from contextlib import asynccontextmanager
from logfire import Logfire as Logfire
from logfire.exceptions import LogfireConfigError as LogfireConfigError
from logfire.propagate import get_context as get_context
from pydantic_monty import AsyncMontyRemote, AsyncMontySession as AsyncMontySession
from typing import Any

class AgentSandboxPool:
    """An async Monty remote pool that adds Logfire hints when checkout is refused.

    Monty's native pool and refusal exception cannot be subclassed. Hinted refusals raise
    RuntimeError, with the original MontyRefusedError available as the chained cause.
    """
    def __init__(self, pool: AsyncMontyRemote) -> None: ...
    async def __aenter__(self) -> AgentSandboxPool: ...
    async def __aexit__(self, *args: Any) -> None: ...
    @asynccontextmanager
    async def checkout(self, **kwargs: Any) -> AsyncGenerator[AsyncMontySession, None]:
        """Check out a Monty session, forwarding all options to AsyncMontyRemote.checkout."""

def agent_sandboxes_url(base_url: str) -> str:
    """Validate and normalize a supplied or derived Logfire Agent Sandboxes URL.

    The client opens its gRPC stream at the root of this URL, so the base URL must not have a path.
    """
def create_agent_sandboxes(logfire_instance: Logfire, *, api_key: str | None, url: str | None, metadata: Callable[[], Mapping[str, str]] | None = None, connect_headers: Callable[[], Mapping[str, str]] | None = None, **kwargs: Any) -> AgentSandboxPool: ...
