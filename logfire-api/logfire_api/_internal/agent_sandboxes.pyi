from collections.abc import Awaitable as Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from logfire import Logfire as Logfire
from logfire.exceptions import LogfireConfigError as LogfireConfigError
from logfire.propagate import get_context as get_context
from pydantic_monty import AsyncMontyRemote, AsyncMontySession as AsyncMontySession, ExternalModule as ExternalModule, OSPolicy, ResourceLimits, TypeCheckFormat
from typing import Any
from typing_extensions import TypedDict, Unpack

class AgentSandboxCheckoutOptions(TypedDict, total=False):
    """Keyword options forwarded unchanged to AsyncMontyRemote.checkout."""
    script_name: str
    limits: ResourceLimits | None
    type_check: bool
    type_check_stubs: str | None
    type_check_format: TypeCheckFormat | None
    type_check_color: bool
    assert_message_annotations: bool | int
    print_flush_interval: float | None
    os_policy: OSPolicy | None
    external_modules: Mapping[str, ExternalModule | Callable[[], Awaitable[ExternalModule]]] | None
    ephemeral: bool | None
    profile: str | None

class AgentSandboxPool:
    """An async Monty remote pool that adds Logfire hints when checkout is refused.

    Monty's native pool and refusal exception cannot be subclassed. Hinted refusals raise
    RuntimeError, with the original MontyRefusedError available as the chained cause.
    """
    def __init__(self, pool: AsyncMontyRemote) -> None: ...
    async def __aenter__(self) -> AgentSandboxPool: ...
    async def __aexit__(self, *args: Any) -> None: ...
    def checkout(self, **kwargs: Unpack[AgentSandboxCheckoutOptions]) -> AbstractAsyncContextManager[AsyncMontySession]:
        """Check out a session with the options and defaults of AsyncMontyRemote.checkout."""

def agent_sandboxes_url(base_url: str) -> str:
    """Validate and normalize a supplied or derived Logfire Agent Sandboxes URL.

    The client opens its gRPC stream at the root of this URL, so the base URL must not have a path.
    """
def create_agent_sandboxes(logfire_instance: Logfire, *, api_key: str | None, url: str | None, metadata: Callable[[], Mapping[str, str]] | None = None, connect_headers: Callable[[], Mapping[str, str]] | None = None, **kwargs: Any) -> AgentSandboxPool: ...
