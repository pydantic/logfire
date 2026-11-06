from __future__ import annotations

import importlib
import shutil
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

import logfire
from logfire._internal import agent_sandboxes as agent_sandboxes_module
from logfire.exceptions import LogfireConfigError
from logfire.testing import TestExporter

API_KEY = 'pylf_v1_eu_0123456789abcdef'


class SandboxServer(grpc.GenericRpcHandler):
    """A local stand-in for the agent sandboxes server.

    Serves the `monty.v1.MontySession/Session` gRPC method and records the path and metadata of each stream.
    It relays each stream to a local `monty subprocess` worker.
    The worker reads and writes protobuf messages framed with a little-endian 4-byte length prefix.
    The server runs in its own threads, so the client and the server do not share the test's event loop.
    """

    def __init__(self) -> None:
        self.requests: list[tuple[str, Mapping[str, str]]] = []
        self.url = ''

    def service(self, handler_call_details: grpc.HandlerCallDetails) -> grpc.RpcMethodHandler[bytes, bytes] | None:
        metadata = {key: value for key, value in handler_call_details.invocation_metadata if isinstance(value, str)}
        self.requests.append((handler_call_details.method, metadata))
        return grpc.stream_stream_rpc_method_handler(self.session)

    def session(self, requests: Iterator[bytes], context: grpc.ServicerContext) -> Iterator[bytes]:
        monty = shutil.which('monty', path=sysconfig.get_path('scripts')) or shutil.which('monty')
        assert monty is not None
        proc = subprocess.Popen([monty, 'subprocess'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
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
    with logfire.span('parent'):
        async with logfire.agent_sandboxes(
            api_key=API_KEY,
            url=sandbox_server.url,
            metadata=lambda: {'x-custom': 'custom-value'},
        ) as pool:
            async with pool.checkout() as session:
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


@pytest.mark.parametrize('base_url', ['https://logfire.example.com/prefix', 'https://logfire.example.com/?x=1'])
def test_agent_sandboxes_url_with_path(base_url: str, config_kwargs: dict[str, Any]) -> None:
    config_kwargs['advanced'].base_url = base_url
    logfire.configure(**config_kwargs)

    with pytest.raises(LogfireConfigError) as exc_info:
        logfire.agent_sandboxes(api_key=API_KEY)
    assert str(exc_info.value) == (
        f'Agent sandboxes are served at the root of the Logfire URL, but the base URL {base_url!r} has a path. '
        'Pass the sandboxes server URL to `logfire.agent_sandboxes(url=...)`.'
    )


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
            'request_timeout': None,
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
