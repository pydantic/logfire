from collections.abc import Callable, Mapping as Mapping
from logfire import Logfire as Logfire
from logfire.exceptions import LogfireConfigError as LogfireConfigError
from logfire.propagate import get_context as get_context
from pydantic_monty import AsyncMontyRemote
from typing import Any

def agent_sandboxes_url(base_url: str) -> str:
    """Return the agent sandboxes server URL for a Logfire HTTP(S) base URL.

    The client opens its gRPC stream at the root of this URL.
    """
def create_agent_sandboxes(logfire_instance: Logfire, *, api_key: str | None, url: str | None, metadata: Callable[[], Mapping[str, str]] | None = None, connect_headers: Callable[[], Mapping[str, str]] | None = None, **kwargs: Any) -> AsyncMontyRemote: ...
