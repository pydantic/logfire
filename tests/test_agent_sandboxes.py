from __future__ import annotations

import asyncio
import importlib
import shutil
import sys
import sysconfig
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest
from inline_snapshot import snapshot
from websockets.asyncio.server import ServerConnection, serve

import logfire
from logfire._internal import agent_sandboxes as agent_sandboxes_module
from logfire._internal.integrations import monty as monty_integration
from logfire.exceptions import LogfireConfigError
from logfire.testing import TestExporter

API_KEY = 'pylf_v1_eu_0123456789abcdef'


class SandboxServer:
    """A local stand-in for the agent sandboxes server.

    Records each WebSocket upgrade request and relays the connection to a local `monty subprocess` worker,
    which reads and writes protobuf messages framed with a little-endian 4-byte length prefix.
    """

    def __init__(self) -> None:
        self.requests: list[tuple[str, Mapping[str, str]]] = []
        self.url = ''

    async def handler(self, ws: ServerConnection) -> None:
        assert ws.request is not None
        self.requests.append((ws.request.path, ws.request.headers))
        monty = shutil.which('monty', path=sysconfig.get_path('scripts')) or shutil.which('monty')
        assert monty is not None
        proc = await asyncio.create_subprocess_exec(
            monty, 'subprocess', stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )
        assert proc.stdin is not None and proc.stdout is not None
        stdin, stdout = proc.stdin, proc.stdout

        async def to_worker() -> None:
            async for message in ws:
                assert isinstance(message, bytes)
                stdin.write(len(message).to_bytes(4, 'little') + message)
                await stdin.drain()

        async def to_client() -> None:
            while True:
                size = int.from_bytes(await stdout.readexactly(4), 'little')
                await ws.send(await stdout.readexactly(size))

        tasks = [asyncio.create_task(to_worker()), asyncio.create_task(to_client())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            proc.kill()
            await proc.wait()


@pytest.fixture
async def sandbox_server() -> AsyncIterator[SandboxServer]:
    server = SandboxServer()
    async with serve(server.handler, '127.0.0.1', 0) as ws_server:
        port = ws_server.sockets[0].getsockname()[1]
        server.url = f'ws://127.0.0.1:{port}/monty-ws/'
        yield server


@pytest.mark.anyio
async def test_agent_sandboxes_run_code(sandbox_server: SandboxServer, exporter: TestExporter) -> None:
    with logfire.span('parent'):
        async with logfire.agent_sandboxes(
            api_key=API_KEY,
            url=sandbox_server.url,
            connect_headers=lambda: {'x-custom': 'custom-value'},
        ) as pool:
            async with pool.checkout() as session:
                assert await session.feed_run('1 + 1') == 2

    [(path, headers)] = sandbox_server.requests
    assert path == '/monty-ws/'
    assert headers['authorization'] == f'Bearer {API_KEY}'
    assert headers['x-custom'] == 'custom-value'

    # Earlier tests may have enabled process-wide Monty instrumentation, adding local spans.
    [parent] = [span for span in exporter.exported_spans_as_dict() if span['name'] == 'parent']
    # The current span is propagated to the server, so the server's spans join this trace.
    assert headers['traceparent'] == f'00-{parent["context"]["trace_id"]:032x}-{parent["context"]["span_id"]:016x}-01'


@pytest.mark.anyio
async def test_agent_sandboxes_instrument_locally(sandbox_server: SandboxServer, exporter: TestExporter) -> None:
    with logfire.span('parent'):
        async with logfire.agent_sandboxes(api_key=API_KEY, url=sandbox_server.url, instrument_locally=True) as pool:
            async with pool.checkout() as session:
                assert await session.feed_run('1 + 1') == 2

    [(_, headers)] = sandbox_server.requests
    spans = exporter.exported_spans_as_dict()
    assert [span['name'] for span in spans] == snapshot(['run code', 'session {script_name}', 'parent'])
    parent = spans[2]
    # Monty's integration sends the span current at checkout, as `logfire.agent_sandboxes()` does without it.
    assert headers['traceparent'] == f'00-{parent["context"]["trace_id"]:032x}-{parent["context"]["span_id"]:016x}-01'


@pytest.mark.anyio
@pytest.mark.parametrize('header_name', ['Authorization', 'authorization', 'aUtHoRiZaTiOn'])
async def test_agent_sandboxes_connect_headers_override(sandbox_server: SandboxServer, header_name: str) -> None:
    async with logfire.agent_sandboxes(
        api_key=API_KEY,
        url=sandbox_server.url,
        connect_headers=lambda: {header_name: 'Bearer other'},
    ) as pool:
        async with pool.checkout() as session:
            assert await session.feed_run('2 * 3') == 6

    [(_, headers)] = sandbox_server.requests
    assert headers['authorization'] == 'Bearer other'


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
        ('pylf_v1_us_abc', None, 'wss://logfire-us.pydantic.dev/monty-ws/'),
        ('pylf_v1_eu_abc', None, 'wss://logfire-eu.pydantic.dev/monty-ws/'),
        ('pylf_v2_stagingeu_abc', None, 'wss://logfire-eu.pydantic.info/monty-ws/'),
        ('pylf_v1_us_abc', 'http://localhost:8000', 'ws://localhost:8000/monty-ws/'),
        ('pylf_v1_us_abc', 'https://logfire.example.com/', 'wss://logfire.example.com/monty-ws/'),
    ],
)
def test_agent_sandboxes_url(
    api_key: str, base_url: str | None, expected: str, config_kwargs: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    config_kwargs['advanced'].base_url = base_url
    logfire.configure(**config_kwargs)
    urls: list[str] = []

    def fake_websocket(url: str, **kwargs: Any) -> str:
        urls.append(url)
        return url

    monkeypatch.setattr(agent_sandboxes_module, 'AsyncMontyWebsocket', fake_websocket)

    logfire.agent_sandboxes(api_key=api_key)
    assert urls == [expected]


@pytest.mark.parametrize('instrument_locally', [True, False])
def test_agent_sandboxes_instrument(instrument_locally: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def instrument_telemetry(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(monty_integration, '_installed', False)
    monkeypatch.setattr(monty_integration, 'instrument_telemetry', instrument_telemetry)

    logfire.agent_sandboxes(api_key=API_KEY, instrument_locally=instrument_locally)

    assert len(calls) == int(instrument_locally)


@pytest.mark.parametrize(
    'options',
    [
        {},
        {'connect_headers': None},
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

    def fake_websocket(url: str, **kwargs: Any) -> None:
        received.update(kwargs)

    monkeypatch.setattr(agent_sandboxes_module, 'AsyncMontyWebsocket', fake_websocket)

    logfire.agent_sandboxes(api_key=API_KEY, **options)

    headers = received.pop('connect_headers')
    assert headers() == {'authorization': f'Bearer {API_KEY}'}
    assert received == {name: value for name, value in options.items() if name != 'connect_headers'}


def test_agent_sandboxes_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, 'pydantic_monty', None)

    with pytest.raises(RuntimeError) as exc_info:
        importlib.reload(agent_sandboxes_module)
    assert str(exc_info.value) == snapshot("""\
`logfire.agent_sandboxes()` requires the `pydantic-monty-client` package.
You can install this with:
    pip install 'logfire[agent-sandboxes]'\
""")
