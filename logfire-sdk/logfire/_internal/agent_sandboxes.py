"""Build authenticated Monty pools for Logfire.agent_sandboxes.

AgentSandboxPool wraps checkout failures in public Agent Sandboxes errors while yielding Monty sessions.
AgentSandboxCheckoutOptions preserves the native checkout options without duplicating their defaults.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from typing_extensions import TypedDict, Unpack

from logfire.exceptions import AgentSandboxConnectionError, AgentSandboxRefusedError, LogfireConfigError
from logfire.propagate import get_context

try:
    from pydantic_monty import AsyncMontyRemote, AsyncMontySession, MontyRefusedError
except ImportError:
    raise RuntimeError(
        '`logfire.agent_sandboxes()` requires the `pydantic-monty-client` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[agent-sandboxes]'"
    ) from None

if TYPE_CHECKING:
    from pydantic_monty import ExternalModule, OSPolicy, ResourceLimits, TypeCheckFormat

    from logfire import Logfire


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
    """An async Monty remote pool with typed Agent Sandboxes checkout errors.

    Refusals raise AgentSandboxRefusedError; connection failures raise AgentSandboxConnectionError.
    The original exception is always the chained cause. Errors inside a checked-out session,
    including user-code exceptions, MontyCrashedError, MontyDisconnectError and MontyShutdown,
    pass through unchanged.
    """

    def __init__(self, pool: AsyncMontyRemote, url: str) -> None:
        self._pool = pool
        self._url = url

    async def __aenter__(self) -> AgentSandboxPool:
        await self._pool.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._pool.__aexit__(*args)

    def checkout(self, **kwargs: Unpack[AgentSandboxCheckoutOptions]) -> AbstractAsyncContextManager[AsyncMontySession]:
        """Check out a session with the options and defaults of AsyncMontyRemote.checkout.

        Monty 1.5.0 uses RuntimeError for connection failures, identified by its URL-qualified
        spawn prefix and a gRPC status, connect timeout or non-gRPC response diagnostic.
        Other RuntimeErrors, including malformed metadata and callback failures, pass through.
        """

        @asynccontextmanager
        async def checkout_session() -> AsyncGenerator[AsyncMontySession, None]:
            async with AsyncExitStack() as stack:
                try:
                    session = await stack.enter_async_context(self._pool.checkout(**kwargs))
                except MontyRefusedError as exc:
                    hint = None
                    if exc.status_code in ('UNAUTHENTICATED', 'PERMISSION_DENIED'):
                        hint = (
                            'Check that you use a project API key (not a personal API key) with the '
                            "`project:execute_agent_sandboxes` scope, that the key's region matches the server URL, "
                            'and that Agent Sandboxes are enabled for the project.'
                        )
                    elif exc.status_code == 'RESOURCE_EXHAUSTED' and exc.cause in ('caller_cap', 'capacity'):
                        hint = 'Lower `max_processes` to open fewer sessions at once, or retry after a delay.'
                    message = f'Agent Sandboxes refused the session: {exc.status_message or str(exc)}'
                    if hint is not None:
                        message += f'\nLogfire Agent Sandboxes: {hint}'
                    raise AgentSandboxRefusedError(
                        message, status_code=exc.status_code, status_message=exc.status_message, reason=exc.cause
                    ) from exc
                except RuntimeError as exc:
                    prefix = f'failed to spawn monty worker: {self._url}: '
                    message = str(exc).removeprefix(prefix)
                    if not str(exc).startswith(prefix) or not re.match(
                        r'(?:[A-Z_]+: |connect timed out after |not a gRPC server, )', message
                    ):
                        raise
                    raise AgentSandboxConnectionError(
                        f'Agent Sandboxes could not connect to {self._url}: {message}'
                    ) from exc
                yield session

        return checkout_session()


def agent_sandboxes_url(base_url: str) -> str:
    """Validate and normalize a supplied or derived Logfire Agent Sandboxes URL.

    The client opens its gRPC stream at the root of this URL, so the base URL must not have a path.
    """
    parts = urlsplit(base_url)
    if parts.path.strip('/') or parts.query or parts.fragment:
        raise LogfireConfigError(
            f'Agent Sandboxes URL {base_url!r} must not contain a path, query, or fragment. '
            'Use only the server origin, such as `https://logfire-us.pydantic.dev`. '
            '`/monty-ws/` was the old path; remove it from the URL.'
        )
    return f'{parts.scheme}://{parts.netloc}'


def create_agent_sandboxes(
    logfire_instance: Logfire,
    *,
    api_key: str | None,
    url: str | None,
    metadata: Callable[[], Mapping[str, str]] | None = None,
    connect_headers: Callable[[], Mapping[str, str]] | None = None,
    **kwargs: Any,
) -> AgentSandboxPool:
    if 'request_timeout' in kwargs and kwargs['request_timeout'] is None:
        raise LogfireConfigError(
            'Logfire Agent Sandboxes require a finite `request_timeout` in seconds; `None` is not supported. '
            'Omit `request_timeout` to use the Monty default (10.0 seconds).'
        )
    if connect_headers is not None:
        if metadata is not None:
            raise TypeError('Pass `metadata` only; `connect_headers` is its deprecated name.')
        warnings.warn(
            '`connect_headers` is deprecated, use `metadata` instead.',
            DeprecationWarning,
            stacklevel=3,
        )
        metadata = connect_headers
    config = logfire_instance.config
    api_key = api_key or config.api_key
    if not api_key:
        raise LogfireConfigError(
            'Agent sandboxes require a Logfire API key with the `project:execute_agent_sandboxes` scope. '
            'Set the LOGFIRE_API_KEY environment variable or pass `api_key` to `logfire.agent_sandboxes()`.'
        )
    url = agent_sandboxes_url(url if url is not None else config.advanced.generate_base_url(api_key))

    user_metadata = metadata

    def session_metadata() -> dict[str, str]:
        # `traceparent` for the current span, so the server's spans for this session join the caller's trace.
        result = {name.lower(): value for name, value in get_context().items()}
        result['authorization'] = f'Bearer {api_key}'
        if user_metadata is not None:
            result.update((name.lower(), value) for name, value in user_metadata().items())
        return result

    return AgentSandboxPool(
        AsyncMontyRemote(
            url,
            metadata=session_metadata,
            **kwargs,
        ),
        url,
    )
