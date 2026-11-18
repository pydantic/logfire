from collections.abc import Callable, Mapping as Mapping
from logfire import Logfire as Logfire
from logfire.exceptions import LogfireConfigError as LogfireConfigError
from logfire.propagate import get_context as get_context
from pydantic_monty import AsyncMontyRemote
from typing import Any

def agent_sandboxes_url(base_url: str) -> str:
    """Validate and normalize a supplied or derived Logfire Agent Sandboxes URL.

    The client opens its gRPC stream at the root of this URL, so the base URL must not have a path.
    """
def create_agent_sandboxes(logfire_instance: Logfire, *, api_key: str | None, url: str | None, metadata: Callable[[], Mapping[str, str]] | None = None, connect_headers: Callable[[], Mapping[str, str]] | None = None, **kwargs: Any) -> AsyncMontyRemote: ...
