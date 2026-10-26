from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from logfire.exceptions import LogfireConfigError

try:
    from pydantic_monty import AsyncMontyWebsocket
except ImportError:
    raise RuntimeError(
        '`logfire.agent_sandboxes()` requires the `pydantic-monty-client` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[agent-sandboxes]'"
    ) from None

if TYPE_CHECKING:
    from logfire import Logfire


def agent_sandboxes_url(base_url: str) -> str:
    """Convert a Logfire HTTP(S) base URL into the agent sandboxes WebSocket URL."""
    scheme, _, rest = base_url.partition('://')
    scheme = {'https': 'wss', 'http': 'ws'}.get(scheme, scheme)
    return f'{scheme}://{rest.rstrip("/")}/monty-ws/'


def create_agent_sandboxes(
    logfire_instance: Logfire,
    *,
    api_key: str | None,
    url: str | None,
    instrument: bool,
    max_processes: int | None,
    checkout_timeout: float | None,
    request_timeout: float | None,
    connect_headers: Callable[[], Mapping[str, str]] | None,
    feed_duration_limit_grace: float | None,
    turn_duration_limit_grace: float | None,
    auto_resume: bool,
) -> AsyncMontyWebsocket:
    config = logfire_instance.config
    api_key = api_key or config.api_key or config.param_manager.load_param('api_key')
    if not api_key:
        raise LogfireConfigError(
            'Agent sandboxes require a Logfire API key with the `project:execute_agent_sandboxes` scope. '
            'Set the LOGFIRE_API_KEY environment variable or pass `api_key` to `logfire.agent_sandboxes()`.'
        )
    if url is None:
        url = agent_sandboxes_url(config.advanced.generate_base_url(api_key))

    if instrument:
        logfire_instance.instrument_monty()

    def headers() -> dict[str, str]:
        result = {'authorization': f'Bearer {api_key}'}
        if connect_headers is not None:
            result.update((name.lower(), value) for name, value in connect_headers().items())
        return result

    return AsyncMontyWebsocket(
        url,
        max_processes=max_processes,
        checkout_timeout=checkout_timeout,
        request_timeout=request_timeout,
        connect_headers=headers,
        feed_duration_limit_grace=feed_duration_limit_grace,
        turn_duration_limit_grace=turn_duration_limit_grace,
        auto_resume=auto_resume,
    )
