from __future__ import annotations

import pickle
import socket
from typing import Any
from unittest.mock import Mock

import pytest
import requests
from urllib3.connection import HTTPConnection

from logfire._internal.auth import UserToken
from logfire._internal.client import LogfireClient
from logfire._internal.config import VariablesOptions
from logfire._internal.exporters.otlp import OTLPExporterHttpSession
from logfire._internal.http_transport import (
    IDLE_CONNECTION_RECYCLE_SECONDS,
    TCP_KEEPALIVE_IDLE_SECONDS,
    LogfireHTTPAdapter,
    _IdleRecyclingPoolMixin,  # pyright: ignore[reportPrivateUsage]
    _pool_classes,  # pyright: ignore[reportPrivateUsage]
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


def test_adapter_passes_socket_options_to_the_pool() -> None:
    adapter = LogfireHTTPAdapter()
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in adapter.poolmanager.connection_pool_kw['socket_options']


def test_explicit_socket_options_are_not_overridden() -> None:
    """`setdefault` semantics: a caller passing their own options keeps them."""
    adapter = LogfireHTTPAdapter()
    adapter.init_poolmanager(1, 1, socket_options=[])
    assert adapter.poolmanager.connection_pool_kw['socket_options'] == []


def test_adapter_registers_the_recycling_pools() -> None:
    adapter = LogfireHTTPAdapter(idle_recycle_seconds=11)
    classes = adapter.poolmanager.pool_classes_by_scheme

    for scheme in ('http', 'https'):
        assert issubclass(classes[scheme], _IdleRecyclingPoolMixin)
        assert classes[scheme].idle_recycle_seconds == 11


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [1000.0]
    # Patch the module's own indirection rather than `time.monotonic`, which urllib3 shares.
    monkeypatch.setattr('logfire._internal.http_transport._now', lambda: now[0])
    return now


def make_pool(monkeypatch: pytest.MonkeyPatch, idle_recycle_seconds: float) -> Any:
    def not_dropped(conn: Any) -> bool:
        return False

    # Mock connections are not real sockets, so urllib3's own liveness check must stand aside.
    monkeypatch.setattr('urllib3.connectionpool.is_connection_dropped', not_dropped)
    pool = _pool_classes(idle_recycle_seconds)['https']('example.com', maxsize=5)
    # urllib3 pre-fills the pool with `None` placeholders; drain them so seeded connections are
    # not discarded as "pool is full".
    while not pool.pool.empty():
        pool.pool.get(block=False)
    return pool


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch, clock: list[float]) -> Any:
    return make_pool(monkeypatch, IDLE_CONNECTION_RECYCLE_SECONDS)


def test_connection_used_within_the_window_is_reused(pool: Any, clock: list[float]) -> None:
    conn = Mock()
    pool._put_conn(conn)

    clock[0] += IDLE_CONNECTION_RECYCLE_SECONDS - 1

    assert pool._get_conn() is conn
    conn.close.assert_not_called()


def test_connection_idle_beyond_the_window_is_closed(pool: Any, clock: list[float]) -> None:
    conn = Mock()
    pool._put_conn(conn)

    clock[0] += IDLE_CONNECTION_RECYCLE_SECONDS + 1

    # urllib3 reconnects lazily, so the connection is still handed back, just closed first.
    assert pool._get_conn() is conn
    conn.close.assert_called_once()


def test_a_busy_session_still_recycles_a_connection_that_sat_idle(pool: Any, clock: list[float]) -> None:
    """Idleness is per connection, not per session.

    One Logfire session carries traces, metrics and logs from different threads. A steady trace
    stream keeps the session busy while the connection that last served a metric export waits out
    the whole export interval, so a session-level clock would never fire for it.
    """
    idle_conn, busy_conn = Mock(name='idle'), Mock(name='busy')
    pool._put_conn(idle_conn)  # parked at the bottom of the LIFO pool
    pool._put_conn(busy_conn)

    # Traffic keeps cycling the top connection well inside the window.
    for _ in range(5):
        clock[0] += IDLE_CONNECTION_RECYCLE_SECONDS / 2
        assert pool._get_conn() is busy_conn
        pool._put_conn(busy_conn)
    busy_conn.close.assert_not_called()

    # The one underneath has been idle the whole time and must not be trusted.
    assert pool._get_conn() is busy_conn
    assert pool._get_conn() is idle_conn
    idle_conn.close.assert_called_once()


def test_recycle_window_is_configurable(monkeypatch: pytest.MonkeyPatch, clock: list[float]) -> None:
    pool = make_pool(monkeypatch, idle_recycle_seconds=5)
    conn = Mock()
    pool._put_conn(conn)

    clock[0] += 6

    pool._get_conn()
    conn.close.assert_called_once()


def test_install_connection_policy_mounts_both_schemes() -> None:
    session = requests.Session()
    install_connection_policy(session)

    http, https = session.get_adapter('http://x'), session.get_adapter('https://x')
    assert isinstance(https, LogfireHTTPAdapter)
    # One adapter for both schemes, so a session has a single pool manager.
    assert http is https


def test_adapter_survives_pickling() -> None:
    """`requests.Session` is picklable, so the adapter must rebuild its pools on unpickling."""
    restored = pickle.loads(pickle.dumps(LogfireHTTPAdapter(idle_recycle_seconds=7)))

    assert isinstance(restored, LogfireHTTPAdapter)
    assert restored.poolmanager.pool_classes_by_scheme['https'].idle_recycle_seconds == 7


def _otlp_exporter_session() -> requests.Session:
    return OTLPExporterHttpSession()


def _logfire_client_session() -> requests.Session:
    token = UserToken(token='abc', base_url='http://localhost', expiration='2099-12-31T23:59:59')
    return LogfireClient(user_token=token)._session  # pyright: ignore[reportPrivateUsage]


def _remote_variables_session() -> requests.Session:
    provider = LogfireRemoteVariableProvider(base_url='https://x', token='t', options=VariablesOptions())
    return provider._session  # pyright: ignore[reportPrivateUsage]


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
