from __future__ import annotations

import importlib
import inspect
import shutil
import socket
import subprocess
import sys
import sysconfig
import threading
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import grpc
import pytest
from inline_snapshot import snapshot
from pydantic_monty import (
    AsyncMontyRemote,
    AsyncMontySession,
    MontyCrashedError,
    MontyDisconnectError,
    MontyRefusedError,
    MontyShutdown,
)

import logfire
from logfire._internal import agent_sandboxes as agent_sandboxes_module
from logfire.exceptions import LogfireConfigError
from logfire.testing import TestExporter

API_KEY = 'pylf_v1_eu_0123456789abcdef'


def test_agent_sandboxes_checkout_signature() -> None:
    """Typed checkout options must match Monty's optional parameters without duplicating their defaults."""
    options = agent_sandboxes_module.AgentSandboxCheckoutOptions
    native = list(inspect.signature(AsyncMontyRemote.checkout).parameters.values())[1:]
    assert options.__optional_keys__ == {param.name for param in native}
    assert not options.__required_keys__
    assert all(param.default is not inspect.Parameter.empty for param in native)
    assert all('Any' not in str(annotation) for annotation in options.__annotations__.values())


class SandboxServer(grpc.GenericRpcHandler):
    """A local stand-in for the agent sandboxes server.

    Serves the `monty.v1.MontySession/Session` gRPC method and records the path and metadata of each stream.
    It relays each stream to a local `monty subprocess` worker.
    The worker reads and writes protobuf messages framed with a little-endian 4-byte length prefix.
    The server runs in its own threads, so the client and the server do not share the test's event loop.
    session_events can supply protobuf ChildEvent replies instead of launching a worker.
    """

    def __init__(self) -> None:
        self.requests: list[tuple[str, Mapping[str, str]]] = []
        self.url = ''
        self.refusal: tuple[grpc.StatusCode, str, str | None] | None = None
        self.session_events: tuple[bytes, ...] | None = None

    def service(self, handler_call_details: grpc.HandlerCallDetails) -> grpc.RpcMethodHandler[bytes, bytes] | None:
        metadata = {key: value for key, value in handler_call_details.invocation_metadata if isinstance(value, str)}
        self.requests.append((handler_call_details.method, metadata))
        return grpc.stream_stream_rpc_method_handler(self.session)

    def session(self, requests: Iterator[bytes], context: grpc.ServicerContext) -> Iterator[bytes]:
        if self.refusal is not None:
            status, message, cause = self.refusal
            if cause is not None:
                context.set_trailing_metadata((('monty-cause', cause),))
            context.abort(status, message)
        if self.session_events is not None:
            context.send_initial_metadata(())
            for event in self.session_events:
                next(requests)
                yield event
            next(requests)
            return
        monty = shutil.which('monty', path=sysconfig.get_path('scripts')) or shutil.which('monty')
        assert monty is not None
        proc = subprocess.Popen([monty, 'subprocess'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        context.add_callback(proc.kill)
        assert proc.stdin is not None and proc.stdout is not None
        stdin, stdout = proc.stdin, proc.stdout
        # The client sends nothing until the server admits the stream with its response headers.
        context.send_initial_metadata(())

        def to_worker() -> None:
            try:
                for message in requests:
                    stdin.write(len(message).to_bytes(4, 'little') + message)
                    stdin.flush()
            except (grpc.RpcError, OSError):
                pass
            finally:
                stdin.close()

        threading.Thread(target=to_worker, daemon=True).start()
        try:
            while len(header := stdout.read(4)) == 4:
                yield stdout.read(int.from_bytes(header, 'little'))
        finally:
            proc.kill()
            proc.wait()
            stdout.close()


@pytest.fixture
def sandbox_server() -> Iterator[SandboxServer]:
    server = SandboxServer()
    grpc_server = grpc.server(ThreadPoolExecutor(max_workers=4), handlers=[server])
    port = grpc_server.add_insecure_port('127.0.0.1:0')
    grpc_server.start()
    server.url = f'http://127.0.0.1:{port}'
    try:
        yield server
    finally:
        grpc_server.stop(grace=None)


@pytest.mark.anyio
async def test_agent_sandboxes_run_code(sandbox_server: SandboxServer, exporter: TestExporter) -> None:
    """The wrapper must yield real Monty sessions and preserve trace propagation and checkout options."""
    with logfire.span('parent'):
        async with logfire.agent_sandboxes(
            api_key=API_KEY,
            url=sandbox_server.url,
            metadata=lambda: {'x-custom': 'custom-value'},
        ) as pool:
            async with pool.checkout(script_name='calculation.py') as session:
                assert isinstance(session, AsyncMontySession)
                assert await session.feed_run('1 + 1') == 2

    [(path, headers)] = sandbox_server.requests
    assert path == '/monty.v1.MontySession/Session'
    assert headers['authorization'] == f'Bearer {API_KEY}'
    assert headers['x-custom'] == 'custom-value'

    # Earlier tests may have enabled process-wide Monty instrumentation, adding local spans.
    [parent] = [span for span in exporter.exported_spans_as_dict() if span['name'] == 'parent']
    # The current span is propagated to the server, so the server's spans join this trace.
    assert headers['traceparent'] == f'00-{parent["context"]["trace_id"]:032x}-{parent["context"]["span_id"]:016x}-01'


@pytest.mark.anyio
@pytest.mark.parametrize('header_name', ['Authorization', 'authorization', 'aUtHoRiZaTiOn'])
async def test_agent_sandboxes_metadata_override(sandbox_server: SandboxServer, header_name: str) -> None:
    async with logfire.agent_sandboxes(
        api_key=API_KEY,
        url=sandbox_server.url,
        metadata=lambda: {header_name: 'Bearer other'},
    ) as pool:
        async with pool.checkout() as session:
            assert await session.feed_run('2 * 3') == 6

    [(_, headers)] = sandbox_server.requests
    assert headers['authorization'] == 'Bearer other'


@pytest.mark.anyio
async def test_agent_sandboxes_connect_headers_deprecated(sandbox_server: SandboxServer) -> None:
    with pytest.warns(DeprecationWarning, match='`connect_headers` is deprecated, use `metadata` instead.'):
        pool = logfire.agent_sandboxes(
            api_key=API_KEY, url=sandbox_server.url, connect_headers=lambda: {'X-Custom': 'old-name'}
        )
    async with pool:
        async with pool.checkout() as session:
            assert await session.feed_run('1') == 1

    [(_, headers)] = sandbox_server.requests
    assert headers['x-custom'] == 'old-name'
    assert headers['authorization'] == f'Bearer {API_KEY}'


def test_agent_sandboxes_metadata_and_connect_headers() -> None:
    with pytest.raises(TypeError, match='Pass `metadata` only; `connect_headers` is its deprecated name.'):
        logfire.agent_sandboxes(api_key=API_KEY, metadata=lambda: {}, connect_headers=lambda: {})


@pytest.mark.anyio
async def test_agent_sandboxes_api_key_from_env(
    sandbox_server: SandboxServer, monkeypatch: pytest.MonkeyPatch, config_kwargs: dict[str, Any]
) -> None:
    monkeypatch.setenv('LOGFIRE_API_KEY', 'pylf_v1_us_fromenv')
    logfire.configure(**config_kwargs)

    async with logfire.agent_sandboxes(url=sandbox_server.url) as pool:
        async with pool.checkout() as session:
            assert await session.feed_run('1') == 1

    [(_, headers)] = sandbox_server.requests
    assert headers['authorization'] == 'Bearer pylf_v1_us_fromenv'


@pytest.mark.anyio
async def test_agent_sandboxes_api_key_from_configure(
    sandbox_server: SandboxServer, config_kwargs: dict[str, Any]
) -> None:
    logfire.configure(**config_kwargs, api_key='pylf_v1_us_fromconfigure')

    async with logfire.agent_sandboxes(url=sandbox_server.url) as pool:
        async with pool.checkout() as session:
            assert await session.feed_run('1') == 1

    [(_, headers)] = sandbox_server.requests
    assert headers['authorization'] == 'Bearer pylf_v1_us_fromconfigure'


def test_agent_sandboxes_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('LOGFIRE_API_KEY', raising=False)

    with pytest.raises(LogfireConfigError) as exc_info:
        logfire.agent_sandboxes()
    assert str(exc_info.value) == snapshot(
        'Agent sandboxes require a Logfire API key with the `project:execute_agent_sandboxes` scope. '
        'Set the LOGFIRE_API_KEY environment variable or pass `api_key` to `logfire.agent_sandboxes()`.'
    )


@pytest.mark.parametrize(
    'api_key,base_url,expected',
    [
        ('pylf_v1_us_abc', None, 'https://logfire-us.pydantic.dev'),
        ('pylf_v1_eu_abc', None, 'https://logfire-eu.pydantic.dev'),
        ('pylf_v2_stagingeu_abc', None, 'https://logfire-eu.pydantic.info'),
        ('pylf_v1_us_abc', 'http://localhost:8000', 'http://localhost:8000'),
        ('pylf_v1_us_abc', 'https://logfire.example.com/', 'https://logfire.example.com'),
    ],
)
def test_agent_sandboxes_url(
    api_key: str, base_url: str | None, expected: str, config_kwargs: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    config_kwargs['advanced'].base_url = base_url
    logfire.configure(**config_kwargs)
    urls: list[str] = []

    def fake_remote(url: str, **kwargs: Any) -> str:
        urls.append(url)
        return url

    monkeypatch.setattr(agent_sandboxes_module, 'AsyncMontyRemote', fake_remote)

    logfire.agent_sandboxes(api_key=api_key)
    assert urls == [expected]


@pytest.mark.parametrize('explicit', [False, True])
@pytest.mark.parametrize(
    'base_url',
    [
        'https://logfire.example.com/prefix',
        'https://logfire.example.com/monty-ws/',
        'https://logfire.example.com/?x=1',
        'https://logfire.example.com/#fragment',
    ],
)
def test_agent_sandboxes_url_with_path(base_url: str, explicit: bool, config_kwargs: dict[str, Any]) -> None:
    """Explicit and derived URLs must use the same origin-only rule and explain the old path."""
    config_kwargs['advanced'].base_url = base_url
    logfire.configure(**config_kwargs)

    with pytest.raises(LogfireConfigError) as exc_info:
        logfire.agent_sandboxes(api_key=API_KEY, url=base_url if explicit else None)
    assert str(exc_info.value) == (
        f'Agent Sandboxes URL {base_url!r} must not contain a path, query, or fragment. '
        'Use only the server origin, such as `https://logfire-us.pydantic.dev`. '
        '`/monty-ws/` was the old path; remove it from the URL.'
    )


@pytest.mark.parametrize('url', ['https://logfire.example.com', 'https://logfire.example.com/'])
def test_agent_sandboxes_explicit_url(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both forms of an explicit server origin must normalize to the URL Monty expects."""
    urls: list[str] = []

    def fake_remote(url: str, **kwargs: Any) -> None:
        urls.append(url)

    monkeypatch.setattr(agent_sandboxes_module, 'AsyncMontyRemote', fake_remote)
    logfire.agent_sandboxes(api_key=API_KEY, url=url)
    assert urls == ['https://logfire.example.com']


def test_agent_sandboxes_request_timeout_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject an unbounded timeout before constructing a client because hosted sessions require a deadline."""

    def unexpected_remote(*args: Any, **kwargs: Any) -> None:
        pytest.fail('The client must not be constructed for an invalid timeout')

    monkeypatch.setattr(agent_sandboxes_module, 'AsyncMontyRemote', unexpected_remote)
    with pytest.raises(LogfireConfigError) as exc_info:
        logfire.agent_sandboxes(api_key=API_KEY, request_timeout=None)
    assert str(exc_info.value) == (
        'Logfire Agent Sandboxes require a finite `request_timeout` in seconds; `None` is not supported. '
        'Omit `request_timeout` to use the Monty default (10.0 seconds).'
    )


@pytest.mark.anyio
@pytest.mark.parametrize('status', [grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED])
async def test_agent_sandboxes_auth_refusal(sandbox_server: SandboxServer, status: grpc.StatusCode) -> None:
    """Auth hints must cover all Logfire checks and keep the real refusal and its metadata as the cause."""
    sandbox_server.refusal = (status, 'unauthenticated', None)
    async with logfire.agent_sandboxes(api_key=API_KEY, url=sandbox_server.url) as pool:
        with pytest.raises(logfire.AgentSandboxRefusedError) as exc_info:
            async with pool.checkout():
                pytest.fail('A refused session must not be yielded')

    error = exc_info.value
    cause = error.__cause__
    assert isinstance(cause, MontyRefusedError)
    assert cause is error.__context__
    assert cause.status_code == status.name
    assert cause.status_message == 'unauthenticated'
    assert error.status_code == cause.status_code
    assert error.status_message == cause.status_message
    assert error.reason == cause.cause
    assert isinstance(error, logfire.AgentSandboxError)
    assert str(error) == (
        'Agent Sandboxes refused the session: unauthenticated\nLogfire Agent Sandboxes: '
        'Check that you use a project API key (not a personal API key) with the '
        "`project:execute_agent_sandboxes` scope, that the key's region matches the server URL, "
        'and that Agent Sandboxes are enabled for the project.'
    )


@pytest.mark.anyio
@pytest.mark.parametrize('cause', ['caller_cap', 'capacity'])
async def test_agent_sandboxes_capacity_refusal(sandbox_server: SandboxServer, cause: str) -> None:
    """Known capacity refusals must suggest fewer concurrent sessions or a delayed retry without retrying."""
    sandbox_server.refusal = (grpc.StatusCode.RESOURCE_EXHAUSTED, 'assignment attempt rate exceeded', cause)
    async with logfire.agent_sandboxes(api_key=API_KEY, url=sandbox_server.url) as pool:
        with pytest.raises(logfire.AgentSandboxRefusedError) as exc_info:
            async with pool.checkout():
                pytest.fail('A refused session must not be yielded')

    original = exc_info.value.__cause__
    assert isinstance(original, MontyRefusedError)
    assert original.status_code == 'RESOURCE_EXHAUSTED'
    assert original.status_message == 'assignment attempt rate exceeded'
    assert original.cause == cause
    assert exc_info.value.status_code == original.status_code
    assert exc_info.value.status_message == original.status_message
    assert exc_info.value.reason == cause
    assert str(exc_info.value) == (
        'Agent Sandboxes refused the session: assignment attempt rate exceeded\nLogfire Agent Sandboxes: '
        'Lower `max_processes` to open fewer sessions at once, or retry after a delay.'
    )
    assert len(sandbox_server.requests) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    'status,cause',
    [
        (grpc.StatusCode.RESOURCE_EXHAUSTED, None),
        (grpc.StatusCode.RESOURCE_EXHAUSTED, 'worker_unavailable'),
        (grpc.StatusCode.UNAVAILABLE, 'capacity'),
        (grpc.StatusCode.FAILED_PRECONDITION, None),
    ],
)
@pytest.mark.parametrize('message', ['server unavailable', ''])
async def test_agent_sandboxes_other_refusal(
    sandbox_server: SandboxServer, status: grpc.StatusCode, cause: str | None, message: str
) -> None:
    """Every refusal is wrapped with copied attributes, even without a hint or status message."""
    sandbox_server.refusal = (status, message, cause)
    async with logfire.agent_sandboxes(api_key=API_KEY, url=sandbox_server.url) as pool:
        with pytest.raises(logfire.AgentSandboxRefusedError) as exc_info:
            async with pool.checkout():
                pytest.fail('A refused session must not be yielded')
    error = exc_info.value
    original = error.__cause__
    assert isinstance(original, MontyRefusedError)
    assert error.status_code == original.status_code == status.name
    assert error.status_message == original.status_message == message
    assert error.reason == original.cause == cause
    assert str(error) == f'Agent Sandboxes refused the session: {message or str(original)}'


@pytest.mark.anyio
async def test_agent_sandboxes_non_refusal(sandbox_server: SandboxServer) -> None:
    """Connection or protocol errors must not receive misleading authentication hints."""
    sandbox_server.refusal = (grpc.StatusCode.UNIMPLEMENTED, 'unknown method', None)
    async with logfire.agent_sandboxes(api_key=API_KEY, url=sandbox_server.url) as pool:
        with pytest.raises(logfire.AgentSandboxConnectionError) as exc_info:
            async with pool.checkout():
                pytest.fail('An invalid server must not yield a session')
    assert type(exc_info.value.__cause__) is RuntimeError
    assert isinstance(exc_info.value, logfire.AgentSandboxError)
    assert str(exc_info.value) == (
        f'Agent Sandboxes could not connect to {sandbox_server.url}: UNIMPLEMENTED: unknown method'
    )


@pytest.mark.anyio
@pytest.mark.parametrize('timeout', [False, True])
async def test_agent_sandboxes_connection_failure(timeout: bool) -> None:
    """Real TCP failures and stalled connections must become connection errors, preserving Monty's cause."""
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        if timeout:
            server.listen()
        url = f'http://127.0.0.1:{server.getsockname()[1]}'
        async with logfire.agent_sandboxes(api_key=API_KEY, url=url, request_timeout=0.1) as pool:
            with pytest.raises(logfire.AgentSandboxConnectionError) as exc_info:
                async with pool.checkout():
                    pytest.fail('An unreachable server must not yield a session')
    original = exc_info.value.__cause__
    assert type(original) is RuntimeError
    assert original is exc_info.value.__context__
    inner = str(original).removeprefix(f'failed to spawn monty worker: {url}: ')
    assert str(exc_info.value) == f'Agent Sandboxes could not connect to {url}: {inner}'
    if timeout:
        assert 'connect timed out after' in inner


@pytest.mark.anyio
async def test_agent_sandboxes_tls_failure(sandbox_server: SandboxServer) -> None:
    """A TLS handshake against a plaintext server must be a connection error, not a refusal."""
    url = sandbox_server.url.replace('http:', 'https:')
    async with logfire.agent_sandboxes(api_key=API_KEY, url=url, request_timeout=0.5) as pool:
        with pytest.raises(logfire.AgentSandboxConnectionError) as exc_info:
            async with pool.checkout():
                pytest.fail('An invalid TLS server must not yield a session')
    assert type(exc_info.value.__cause__) is RuntimeError
    assert str(exc_info.value).startswith(f'Agent Sandboxes could not connect to {url}: ')


@pytest.mark.anyio
@pytest.mark.parametrize('metadata', [{'bad header': 'value'}, {'x-header': 'bad\nvalue'}])
async def test_agent_sandboxes_invalid_metadata(metadata: dict[str, str], sandbox_server: SandboxServer) -> None:
    """Invalid metadata is a programming error, even though Monty uses the same spawn-error prefix."""
    async with logfire.agent_sandboxes(api_key=API_KEY, url=sandbox_server.url, metadata=lambda: metadata) as pool:
        with pytest.raises(RuntimeError, match='metadata entry') as exc_info:
            async with pool.checkout():
                pytest.fail('Invalid metadata must not yield a session')
    assert type(exc_info.value) is RuntimeError
    assert exc_info.value.__cause__ is None
    assert not sandbox_server.requests


@pytest.mark.anyio
async def test_agent_sandboxes_metadata_error(sandbox_server: SandboxServer) -> None:
    """Exceptions from a caller's metadata callback must propagate as the exact original object."""
    original = RuntimeError('no token available')

    def metadata() -> Mapping[str, str]:
        raise original

    async with logfire.agent_sandboxes(api_key=API_KEY, url=sandbox_server.url, metadata=metadata) as pool:
        with pytest.raises(RuntimeError) as exc_info:
            async with pool.checkout():
                pytest.fail('A failed callback must not yield a session')
    assert exc_info.value is original
    assert original.__cause__ is None


@pytest.mark.anyio
async def test_agent_sandboxes_inactive_pool() -> None:
    """Forgetting to enter the pool is a programming error, not a server connection failure."""
    pool = logfire.agent_sandboxes(api_key=API_KEY)
    with pytest.raises(RuntimeError, match='pool is not active') as exc_info:
        async with pool.checkout():
            pytest.fail('An inactive pool must not yield a session')
    assert type(exc_info.value) is RuntimeError


@pytest.mark.anyio
@pytest.mark.parametrize('error_type', [ValueError, RuntimeError])
async def test_agent_sandboxes_body_error(sandbox_server: SandboxServer, error_type: type[Exception]) -> None:
    """Errors from user code inside a successful checkout must pass through unchanged and release the session."""
    original = error_type(f'failed to spawn monty worker: {sandbox_server.url}: UNAVAILABLE: user error')
    async with logfire.agent_sandboxes(api_key=API_KEY, url=sandbox_server.url, max_processes=1) as pool:
        with pytest.raises(error_type, match='user error') as exc_info:
            async with pool.checkout():
                raise original
        assert exc_info.value is original
        assert original.__cause__ is None
        async with pool.checkout() as session:
            assert await session.feed_run('1') == 1


@pytest.mark.anyio
async def test_agent_sandboxes_body_refusal(sandbox_server: SandboxServer) -> None:
    """A refusal raised inside the checkout body must not be wrapped as a checkout failure."""
    sandbox_server.refusal = (grpc.StatusCode.UNAUTHENTICATED, 'unauthenticated', None)
    async with logfire.agent_sandboxes(api_key=API_KEY, url=sandbox_server.url) as pool:
        with pytest.raises(logfire.AgentSandboxRefusedError) as refused:
            async with pool.checkout():
                pytest.fail('A refused session must not be yielded')
        original = refused.value.__cause__
        assert isinstance(original, MontyRefusedError)
        sandbox_server.refusal = None
        with pytest.raises(MontyRefusedError) as body_error:
            async with pool.checkout():
                raise original
        assert body_error.value is original


@pytest.mark.anyio
@pytest.mark.parametrize(
    'events,error_type',
    [
        (None, MontyCrashedError),
        ((b'\x52\x00',), MontyDisconnectError),
        ((b'\x52\x00', b'\x62\x09\x0a\x07session'), MontyShutdown),
    ],
)
async def test_agent_sandboxes_session_failure(
    sandbox_server: SandboxServer, events: tuple[bytes, ...] | None, error_type: type[Exception]
) -> None:
    """Native crash, disconnect and shutdown errors from real session operations must pass through unchanged.

    The synthetic replies encode an empty Ok event (field 10), followed for shutdown by
    a Shutdown event (field 12) carrying the synthetic session ID "session".
    """
    sandbox_server.session_events = events
    caught: list[Exception] = []
    async with logfire.agent_sandboxes(
        api_key=API_KEY, url=sandbox_server.url, request_timeout=0.5, auto_resume=False
    ) as pool:
        with pytest.raises(error_type) as exc_info:
            async with pool.checkout() as session:
                try:
                    await session.feed_run('while True: pass' if events is None else '1 + 1')
                except Exception as exc:
                    caught.append(exc)
                    raise
    assert exc_info.value is caught[0]
    assert exc_info.value.__cause__ is None


@pytest.mark.parametrize(
    'options',
    [
        {},
        {'metadata': None},
        {
            'max_processes': 2,
            'checkout_timeout': 3.0,
            'request_timeout': 4.0,
            'feed_duration_limit_grace': 5.0,
            'turn_duration_limit_grace': 6.0,
            'auto_resume': True,
        },
        {
            'max_processes': None,
            'checkout_timeout': None,
            'feed_duration_limit_grace': None,
            'turn_duration_limit_grace': None,
            'auto_resume': False,
        },
        {'future_option': 'custom-value'},
    ],
)
def test_agent_sandboxes_pool_options(options: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    received: dict[str, Any] = {}

    def fake_remote(url: str, **kwargs: Any) -> None:
        received.update(kwargs)

    monkeypatch.setattr(agent_sandboxes_module, 'AsyncMontyRemote', fake_remote)

    logfire.agent_sandboxes(api_key=API_KEY, **options)

    metadata = received.pop('metadata')
    assert metadata() == {'authorization': f'Bearer {API_KEY}'}
    assert received == {name: value for name, value in options.items() if name != 'metadata'}


def test_agent_sandboxes_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, 'pydantic_monty', None)

    with pytest.raises(RuntimeError) as exc_info:
        importlib.reload(agent_sandboxes_module)
    assert str(exc_info.value) == snapshot("""\
`logfire.agent_sandboxes()` requires the `pydantic-monty-client` package.
You can install this with:
    pip install 'logfire[agent-sandboxes]'\
""")
