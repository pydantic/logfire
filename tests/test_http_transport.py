from __future__ import annotations

import pickle
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
import requests
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.poolmanager import PoolManager

from logfire._internal.auth import UserToken
from logfire._internal.client import LogfireClient
from logfire._internal.config import VariablesOptions
from logfire._internal.exporters.otlp import OTLPExporterHttpSession
from logfire._internal.http_transport import (
    IDLE_CONNECTION_RECYCLE_SECONDS,
    TCP_KEEPALIVE_IDLE_SECONDS,
    LogfireHTTPAdapter,
    _IdleRecyclingPoolMixin,  # pyright: ignore[reportPrivateUsage]
    _install_recycling_pools,  # pyright: ignore[reportPrivateUsage]
    _recycling_pool_class,  # pyright: ignore[reportPrivateUsage]
    install_connection_policy,
    keepalive_socket_options,
)
from logfire.variables.remote import LogfireRemoteVariableProvider


def test_keepalive_socket_options_enable_keepalive_and_keep_urllib3_defaults() -> None:
    options = keepalive_socket_options()

    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in options
    # TCP_NODELAY is urllib3's own default and must survive.
    for default in HTTPConnection.default_socket_options:
        assert default in options


def test_keepalive_idle_option_is_set_on_platforms_that_have_one() -> None:
    names = [name for name in ('TCP_KEEPIDLE', 'TCP_KEEPALIVE') if hasattr(socket, name)]
    if not names:  # pragma: no cover
        pytest.skip('platform exposes no keepalive idle option')

    idle_options = {getattr(socket, name) for name in names}
    values = [value for (_level, option, value) in keepalive_socket_options() if option in idle_options]
    assert values == [TCP_KEEPALIVE_IDLE_SECONDS]


def test_the_macos_spelling_of_the_idle_option_is_used_when_it_is_the_only_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linux calls it TCP_KEEPIDLE, macOS calls the same thing TCP_KEEPALIVE."""
    monkeypatch.delattr(socket, 'TCP_KEEPIDLE', raising=False)
    monkeypatch.setattr(socket, 'TCP_KEEPALIVE', 0x10, raising=False)

    assert (socket.IPPROTO_TCP, 0x10, TCP_KEEPALIVE_IDLE_SECONDS) in keepalive_socket_options()


def test_a_platform_missing_an_option_still_gets_the_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ('TCP_KEEPIDLE', 'TCP_KEEPALIVE', 'TCP_KEEPINTVL', 'TCP_KEEPCNT'):
        monkeypatch.delattr(socket, name, raising=False)

    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in keepalive_socket_options()


def test_a_platform_without_keepalive_leaves_the_defaults_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(socket, 'SO_KEEPALIVE', raising=False)

    assert keepalive_socket_options() == list(HTTPConnection.default_socket_options)


def test_a_connection_class_without_default_socket_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """Under Pyodide `urllib3` swaps in an Emscripten connection that has no defaults at all."""

    class EmscriptenLikeConnection:
        pass

    monkeypatch.setattr('urllib3.connection.HTTPConnection', EmscriptenLikeConnection)
    options = keepalive_socket_options()

    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in options
    for default in HTTPConnection.default_socket_options:
        assert default not in options


def test_adapter_passes_socket_options_to_the_pool() -> None:
    adapter = LogfireHTTPAdapter()
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in adapter.poolmanager.connection_pool_kw['socket_options']


def test_explicit_socket_options_are_not_overridden() -> None:
    """`setdefault` semantics: a caller passing their own options keeps them."""
    adapter = LogfireHTTPAdapter()
    adapter.init_poolmanager(1, 1, socket_options=[])
    assert adapter.poolmanager.connection_pool_kw['socket_options'] == []


@pytest.mark.parametrize(
    ('base', 'expected_connection', 'expected_scheme'),
    [
        (HTTPConnectionPool, HTTPConnection, 'http'),
        (HTTPSConnectionPool, HTTPSConnection, 'https'),
    ],
)
def test_derived_pools_keep_their_own_connection_class(
    base: type[HTTPConnectionPool], expected_connection: type[HTTPConnection], expected_scheme: str
) -> None:
    """The mixin must not shadow `ConnectionCls`, or HTTPS pools would open plaintext connections.

    It inherits `HTTPConnectionPool` so the `super()` calls resolve for type checking, which
    raises the fair question of whether an HTTPS pool then builds plain `HTTPConnection`s. It does
    not: the mixin defines neither `ConnectionCls` nor `scheme` in its own `__dict__`, and
    attribute lookup walks each class's own `__dict__` along the MRO, so `HTTPSConnectionPool`
    is the first to supply them.
    """
    cls = _recycling_pool_class(base)

    assert cls.ConnectionCls is expected_connection
    assert cls.scheme == expected_scheme
    assert 'ConnectionCls' not in _IdleRecyclingPoolMixin.__dict__
    assert 'scheme' not in _IdleRecyclingPoolMixin.__dict__


def test_adapter_registers_the_recycling_pools() -> None:
    classes = LogfireHTTPAdapter().poolmanager.pool_classes_by_scheme

    for scheme in ('http', 'https'):
        assert issubclass(classes[scheme], _IdleRecyclingPoolMixin)


def test_adapters_share_their_recycling_pool_classes() -> None:
    """Sessions are built repeatedly, one per SSE reconnect, so the derived classes are cached."""
    first = LogfireHTTPAdapter().poolmanager.pool_classes_by_scheme['https']
    second = LogfireHTTPAdapter().poolmanager.pool_classes_by_scheme['https']

    assert first is second


class _PortEchoHandler(BaseHTTPRequestHandler):
    """Replies with the client's port, which identifies the connection a request arrived on."""

    protocol_version = 'HTTP/1.1'

    def do_GET(self) -> None:
        if self.path == '/drop':
            # Close without replying, so the request fails.
            self.close_connection = True
            return
        body = str(self.client_address[1]).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def server_url() -> Iterator[str]:
    server = ThreadingHTTPServer(('127.0.0.1', 0), _PortEchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def session() -> Iterator[requests.Session]:
    with requests.Session() as session:
        install_connection_policy(session)
        yield session


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [1000.0]
    # Patch the module's own indirection rather than `time.monotonic`, which urllib3 shares.
    monkeypatch.setattr('logfire._internal.http_transport._now', lambda: now[0])
    return now


def test_keepalive_reaches_the_socket(session: requests.Session, server_url: str) -> None:
    response = session.get(server_url, stream=True)
    connection: Any = response.raw.connection
    sock: socket.socket = connection.sock
    # Linux calls it TCP_KEEPIDLE, macOS TCP_KEEPALIVE; looked up by name so either type checks.
    idle_option: int = getattr(socket, 'TCP_KEEPIDLE' if hasattr(socket, 'TCP_KEEPIDLE') else 'TCP_KEEPALIVE')

    assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)
    assert sock.getsockopt(socket.IPPROTO_TCP, idle_option) == TCP_KEEPALIVE_IDLE_SECONDS
    # urllib3's own default survives.
    assert sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
    # Reading the body hands the connection back to the pool, to be closed cleanly with the session.
    assert response.content


def test_connection_is_reused_within_the_window_and_replaced_beyond_it(
    session: requests.Session, server_url: str, clock: list[float]
) -> None:
    first_port = session.get(server_url).text

    clock[0] += IDLE_CONNECTION_RECYCLE_SECONDS - 1
    assert session.get(server_url).text == first_port

    clock[0] += IDLE_CONNECTION_RECYCLE_SECONDS + 1
    assert session.get(server_url).text != first_port


def test_a_busy_session_still_recycles_a_connection_that_sat_idle(
    session: requests.Session, server_url: str, clock: list[float]
) -> None:
    """Idleness is per connection, not per session.

    One Logfire session carries traces, metrics and logs from different threads. A steady trace
    stream keeps the session busy while the connection that last served a metric export waits out
    the whole export interval, so a session-level clock would never fire for it.

    This is the LIFO shape that makes the window matter: sequential traffic reuses whatever sits
    on top of the stack, so a connection opened during a brief overlap is left underneath and
    goes cold, then gets handed back out at the next overlap. Measured on a real session, 98 of
    99 requests went to one connection while another was used once and abandoned.
    """
    # Two overlapping requests open two connections. Reading a body returns its connection to the
    # pool, so the first one read ends up underneath.
    parked = session.get(server_url, stream=True)
    busy = session.get(server_url, stream=True)
    parked_port, busy_port = parked.text, busy.text

    # Sequential traffic keeps cycling the top connection well inside the window.
    for _ in range(5):
        clock[0] += IDLE_CONNECTION_RECYCLE_SECONDS / 2
        assert session.get(server_url).text == busy_port

    # The next overlap reaches the one underneath, idle all along, which must not be trusted.
    top = session.get(server_url, stream=True)
    underneath = session.get(server_url, stream=True)
    assert top.text == busy_port
    assert underneath.text not in (parked_port, busy_port)


def test_a_failed_request_does_not_break_the_pool(session: requests.Session, server_url: str) -> None:
    """`urllib3` puts `None` back in the pool in place of a connection a request broke."""
    with pytest.raises(requests.ConnectionError):
        session.get(f'{server_url}/drop')

    assert session.get(server_url).text


def test_recycling_pools_are_derived_from_the_classes_the_manager_already_uses() -> None:
    """A SOCKS proxy manager brings pool classes of its own, which must not be replaced."""

    class CustomPool(HTTPSConnectionPool):
        pass

    manager = PoolManager()
    manager.pool_classes_by_scheme = {'https': CustomPool}  # pyright: ignore[reportAttributeAccessIssue]

    _install_recycling_pools(manager)

    installed = manager.pool_classes_by_scheme['https']
    assert issubclass(installed, CustomPool)
    assert issubclass(installed, _IdleRecyclingPoolMixin)


def test_proxied_requests_get_the_policy_too() -> None:
    """`requests` builds a separate manager per proxy, which `init_poolmanager` never sees."""
    manager = LogfireHTTPAdapter().proxy_manager_for('http://proxy.example.com')

    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in manager.connection_pool_kw['socket_options']
    assert issubclass(manager.pool_classes_by_scheme['https'], _IdleRecyclingPoolMixin)


def test_a_reused_proxy_manager_is_handed_back_as_is() -> None:
    """`requests` asks for the proxy manager on every proxied request and caches it."""
    adapter = LogfireHTTPAdapter()
    proxy = 'http://proxy.example.com'

    first = adapter.proxy_manager_for(proxy)
    classes = first.pool_classes_by_scheme

    assert adapter.proxy_manager_for(proxy) is first
    assert first.pool_classes_by_scheme is classes


def test_proxied_requests_recycle_idle_connections(server_url: str, clock: list[float]) -> None:
    """A proxied session reuses a fresh connection to the proxy and replaces an idle one.

    The test server doubles as the proxy: `urllib3` sends it the absolute URL, and it replies
    with the port of the connection the request arrived on, as it does for a direct request.
    """
    with requests.Session() as session:
        session.trust_env = False
        session.proxies = {'http': server_url}
        install_connection_policy(session)
        url = 'http://example.invalid/'

        first_port = session.get(url).text

        clock[0] += IDLE_CONNECTION_RECYCLE_SECONDS - 1
        assert session.get(url).text == first_port

        clock[0] += IDLE_CONNECTION_RECYCLE_SECONDS + 1
        assert session.get(url).text != first_port


def test_a_proxy_manager_is_not_handed_out_before_it_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """`requests` caches a new proxy manager before `LogfireHTTPAdapter` configures it.

    A second thread asking for the same proxy in that window must wait for the configured
    manager rather than take the cached one, or its pools would never recycle idle connections.
    """
    adapter = LogfireHTTPAdapter()
    proxy = 'http://proxy.example.com'
    seen_by_other_thread: list[type[HTTPConnectionPool]] = []

    def other_thread() -> None:
        manager = adapter.proxy_manager_for(proxy)
        seen_by_other_thread.append(manager.pool_classes_by_scheme['http'])

    thread = threading.Thread(target=other_thread)

    def install_while_another_thread_asks(manager: PoolManager) -> None:
        # The new manager is already in the `requests` cache at this point.
        assert adapter.proxy_manager[proxy] is manager
        thread.start()
        # Give the other thread the chance to take the unconfigured manager, if it can.
        thread.join(timeout=0.2)
        _install_recycling_pools(manager)

    monkeypatch.setattr('logfire._internal.http_transport._install_recycling_pools', install_while_another_thread_asks)

    manager = adapter.proxy_manager_for(proxy)
    thread.join()

    assert issubclass(manager.pool_classes_by_scheme['http'], _IdleRecyclingPoolMixin)
    assert len(seen_by_other_thread) == 1
    assert issubclass(seen_by_other_thread[0], _IdleRecyclingPoolMixin)


def test_install_connection_policy_mounts_both_schemes() -> None:
    session = requests.Session()
    install_connection_policy(session)

    http, https = session.get_adapter('http://x'), session.get_adapter('https://x')
    assert isinstance(https, LogfireHTTPAdapter)
    # One adapter for both schemes, so a session has a single pool manager.
    assert http is https


def test_adapter_survives_pickling() -> None:
    """`requests.Session` is picklable, so the adapter must rebuild its pools on unpickling."""
    restored = pickle.loads(pickle.dumps(LogfireHTTPAdapter()))

    assert isinstance(restored, LogfireHTTPAdapter)
    assert issubclass(restored.poolmanager.pool_classes_by_scheme['https'], _IdleRecyclingPoolMixin)


def _otlp_exporter_session() -> requests.Session:
    return OTLPExporterHttpSession()


def _logfire_client_session() -> requests.Session:
    token = UserToken(token='abc', base_url='http://localhost', expiration='2099-12-31T23:59:59')
    return LogfireClient(user_token=token)._session  # pyright: ignore[reportPrivateUsage]


def _remote_variables_session() -> requests.Session:
    provider = LogfireRemoteVariableProvider(base_url='https://x', token='t', options=VariablesOptions())
    return provider._session  # pyright: ignore[reportPrivateUsage]


def test_the_sse_stream_session_gets_the_policy() -> None:
    """The SSE stream is read with no read timeout, so TCP keepalive matters most there.

    After a silent drop only a failed keepalive probe unblocks the read. The stream is built by its
    own session rather than the polling one, so covering the provider's polling session says
    nothing about it.
    """
    provider = LogfireRemoteVariableProvider(base_url='https://x', token='t', options=VariablesOptions())

    with provider._new_sse_session() as session:  # pyright: ignore[reportPrivateUsage]
        adapter = session.get_adapter('https://example.com')
        assert isinstance(adapter, LogfireHTTPAdapter)
        assert issubclass(adapter.poolmanager.pool_classes_by_scheme['https'], _IdleRecyclingPoolMixin)
        # Still the SSE session, not the polling one.
        assert session.headers['Accept'] == 'text/event-stream'


@pytest.mark.parametrize(
    'make_session',
    [
        pytest.param(_otlp_exporter_session, id='otlp-exporter'),
        pytest.param(_logfire_client_session, id='logfire-client'),
        pytest.param(_remote_variables_session, id='remote-variables'),
    ],
)
def test_sessions_logfire_owns_get_the_policy(make_session: Any) -> None:
    session = make_session()
    adapter = session.get_adapter('https://example.com')

    assert isinstance(adapter, LogfireHTTPAdapter)
    assert issubclass(adapter.poolmanager.pool_classes_by_scheme['https'], _IdleRecyclingPoolMixin)
