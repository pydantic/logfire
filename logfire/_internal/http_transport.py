"""Connection reuse policy for the HTTP sessions Logfire owns.

`requests` and `urllib3` pool connections indefinitely: there is no maximum age and no idle
expiry. `urllib3` discards a pooled connection only when it can *see* that the peer closed it
(`is_connection_dropped` spots a FIN or RST). A connection dropped silently while idle — a NAT
or stateful firewall reclaiming the flow, which is common on container platforms — still looks
healthy from this side, so the next export writes into it and then blocks until the read
timeout expires. For the metrics exporter, which exports once a minute by default, that is a ten
second stall surfaced as `Read timed out`.

Every session Logfire creates therefore gets two measures:

- **TCP keepalive**, so an idle connection keeps producing traffic and the flow is not reclaimed.
- **An idle recycle window**, so a session unused for longer than the window drops its pooled
  connections and reconnects rather than gambling on one that may already be dead.

This applies only to sessions Logfire itself creates. Clients belonging to the user are
instrumented, never reconfigured.
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

from requests import Session
from requests.adapters import DEFAULT_POOLBLOCK, HTTPAdapter
from urllib3.connection import HTTPConnection

IDLE_CONNECTION_RECYCLE_SECONDS = 30
"""Drop pooled connections when the session has gone unused for longer than this.

Chosen to sit below the things that would otherwise reclaim the connection first: the default
60 second metric export interval (`OTEL_METRIC_EXPORT_INTERVAL`), and the idle timeouts of
typical NAT and load balancer hops, which start around 60 seconds. For reference `httpx`
defaults to 5 seconds and Go's `http.Transport` to 90.
"""

TCP_KEEPALIVE_IDLE_SECONDS = 30
"""Start sending keepalive probes once the connection has been idle this long."""

TCP_KEEPALIVE_INTERVAL_SECONDS = 10
"""Gap between individual keepalive probes."""

TCP_KEEPALIVE_FAILED_PROBES = 3
"""Unanswered probes before the connection is considered dead."""


def keepalive_socket_options() -> list[tuple[int, int, int | bytes]]:
    """`urllib3`'s default socket options plus TCP keepalive.

    Building on `HTTPConnection.default_socket_options` keeps `TCP_NODELAY`, which `urllib3` sets
    and which we have no reason to drop.
    """
    options: list[tuple[int, int, int | bytes]] = [
        *HTTPConnection.default_socket_options,
        (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
    ]

    def add_if_supported(name: str, value: int) -> bool:
        # Looked up by name because these constants are platform specific: referring to them
        # directly would not type check on a platform that lacks them.
        option = getattr(socket, name, None)
        if option is None:
            return False
        options.append((socket.IPPROTO_TCP, option, value))
        return True

    # How long a connection may be idle before probing starts. Without this the system default
    # applies, which is two hours on most platforms and so useless against a NAT timeout.
    # Linux (and recent Windows) call it TCP_KEEPIDLE; macOS calls the same thing TCP_KEEPALIVE.
    if not add_if_supported('TCP_KEEPIDLE', TCP_KEEPALIVE_IDLE_SECONDS):
        add_if_supported('TCP_KEEPALIVE', TCP_KEEPALIVE_IDLE_SECONDS)
    add_if_supported('TCP_KEEPINTVL', TCP_KEEPALIVE_INTERVAL_SECONDS)
    add_if_supported('TCP_KEEPCNT', TCP_KEEPALIVE_FAILED_PROBES)

    return options


class LogfireHTTPAdapter(HTTPAdapter):
    """A `requests` adapter that enables TCP keepalive and recycles idle pooled connections."""

    # `_recycle_lock` holds a lock, which cannot be pickled, so it is rebuilt in `__setstate__`
    # rather than listed here.
    __attrs__ = [*HTTPAdapter.__attrs__, '_idle_recycle_seconds']

    def __init__(
        self,
        *args: Any,
        idle_recycle_seconds: float = IDLE_CONNECTION_RECYCLE_SECONDS,
        **kwargs: Any,
    ) -> None:
        # Set before `super().__init__`, which calls `init_poolmanager`.
        self._idle_recycle_seconds = idle_recycle_seconds
        self._recycle_lock = threading.Lock()
        self._last_used = time.monotonic()
        super().__init__(*args, **kwargs)

    def init_poolmanager(
        self, connections: int, maxsize: int, block: bool = DEFAULT_POOLBLOCK, **pool_kwargs: Any
    ) -> None:
        pool_kwargs.setdefault('socket_options', keepalive_socket_options())
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

    def __setstate__(self, state: dict[str, Any]) -> None:
        self._recycle_lock = threading.Lock()
        self._last_used = time.monotonic()
        state.setdefault('_idle_recycle_seconds', IDLE_CONNECTION_RECYCLE_SECONDS)
        super().__setstate__(state)  # type: ignore[misc]

    def send(self, *args: Any, **kwargs: Any) -> Any:
        with self._recycle_lock:
            if time.monotonic() - self._last_used > self._idle_recycle_seconds:
                # Only idle connections sit in the pool. Anything in flight has been checked out
                # and is untouched by this, so concurrent requests are not disturbed.
                self.poolmanager.clear()
            self._last_used = time.monotonic()
        try:
            return super().send(*args, **kwargs)
        finally:
            # Stamp again on the way out so that a slow or streaming response does not make the
            # *next* request look as though it followed an idle gap.
            with self._recycle_lock:
                self._last_used = time.monotonic()


def install_connection_policy(session: Session, *, idle_recycle_seconds: float | None = None) -> None:
    """Apply the keepalive and idle recycle policy to a session Logfire owns.

    A single adapter serves both schemes so that idleness is tracked per session rather than per
    scheme; a session that talks only HTTPS would otherwise leave the HTTP adapter's clock
    permanently stale.
    """
    kwargs: dict[str, Any] = {} if idle_recycle_seconds is None else {'idle_recycle_seconds': idle_recycle_seconds}
    adapter = LogfireHTTPAdapter(**kwargs)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
