from __future__ import annotations

import pickle
import socket
from typing import Any
from unittest.mock import Mock

import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection

from logfire._internal.auth import UserToken
from logfire._internal.client import LogfireClient
from logfire._internal.config import VariablesOptions
from logfire._internal.exporters.otlp import OTLPExporterHttpSession
from logfire._internal.http_transport import (
    IDLE_CONNECTION_RECYCLE_SECONDS,
    TCP_KEEPALIVE_IDLE_SECONDS,
    LogfireHTTPAdapter,
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


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [1000.0]
    monkeypatch.setattr('logfire._internal.http_transport.time.monotonic', lambda: now[0])
    return now


@pytest.fixture
def make_adapter(monkeypatch: pytest.MonkeyPatch, clock: list[float]):
    """Build a real adapter whose network send is stubbed and whose pool clears are recorded."""

    def factory(*, send_duration: float = 0.0, **kwargs: Any) -> LogfireHTTPAdapter:
        def fake_send(self: HTTPAdapter, *args: Any, **kw: Any) -> Any:
            clock[0] += send_duration
            return Mock()

        monkeypatch.setattr(HTTPAdapter, 'send', fake_send)
        adapter = LogfireHTTPAdapter(**kwargs)
        adapter.poolmanager = Mock(wraps=adapter.poolmanager)
        return adapter

    return factory


def test_pool_is_not_cleared_within_the_idle_window(make_adapter: Any, clock: list[float]) -> None:
    adapter = make_adapter()
    clock[0] += IDLE_CONNECTION_RECYCLE_SECONDS - 1
    adapter.send(Mock())
    adapter.poolmanager.clear.assert_not_called()


def test_pool_is_cleared_after_the_idle_window(make_adapter: Any, clock: list[float]) -> None:
    adapter = make_adapter()
    clock[0] += IDLE_CONNECTION_RECYCLE_SECONDS + 1
    adapter.send(Mock())
    adapter.poolmanager.clear.assert_called_once()


def test_steady_use_never_clears_the_pool(make_adapter: Any, clock: list[float]) -> None:
    """A session used more often than the window keeps its connections."""
    adapter = make_adapter()
    for _ in range(10):
        clock[0] += IDLE_CONNECTION_RECYCLE_SECONDS / 2
        adapter.send(Mock())
    adapter.poolmanager.clear.assert_not_called()


def test_a_slow_response_does_not_count_as_idleness(make_adapter: Any, clock: list[float]) -> None:
    """The clock is stamped on completion, so a long read must not trigger the next clear."""
    adapter = make_adapter(send_duration=IDLE_CONNECTION_RECYCLE_SECONDS * 3)

    adapter.send(Mock())
    adapter.poolmanager.clear.assert_not_called()

    clock[0] += 1
    adapter.send(Mock())
    adapter.poolmanager.clear.assert_not_called()


def test_idle_recycle_seconds_is_configurable(make_adapter: Any, clock: list[float]) -> None:
    adapter = make_adapter(idle_recycle_seconds=5)
    clock[0] += 6
    adapter.send(Mock())
    adapter.poolmanager.clear.assert_called_once()


def test_install_connection_policy_mounts_both_schemes() -> None:
    session = requests.Session()
    install_connection_policy(session)

    http, https = session.get_adapter('http://x'), session.get_adapter('https://x')
    assert isinstance(https, LogfireHTTPAdapter)
    # One adapter for both schemes, so idleness is tracked per session.
    assert http is https


def test_adapter_survives_pickling() -> None:
    """`requests.Session` is picklable and the lock is not, so it must be rebuilt on unpickling."""
    restored = pickle.loads(pickle.dumps(LogfireHTTPAdapter(idle_recycle_seconds=7)))

    assert isinstance(restored, LogfireHTTPAdapter)
    assert restored._idle_recycle_seconds == 7  # pyright: ignore[reportPrivateUsage]
    # Without a rebuilt lock this would raise AttributeError rather than reach the stubbed send.
    assert restored._recycle_lock is not None  # pyright: ignore[reportPrivateUsage]


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
    assert isinstance(session.get_adapter('https://example.com'), LogfireHTTPAdapter)
