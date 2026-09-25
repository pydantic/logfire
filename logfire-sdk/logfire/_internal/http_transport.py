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
- **An idle recycle window**, so a pooled connection unused for longer than the window is closed
  and reconnected rather than gambling on one that may already be dead.

This applies only to sessions Logfire itself creates. Clients belonging to the user are
instrumented, never reconfigured.
"""

from __future__ import annotations

import functools
import socket
import threading
import time
from typing import Any

from requests import Session
from requests.adapters import DEFAULT_POOLBLOCK, HTTPAdapter
from urllib3 import connection as urllib3_connection
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.poolmanager import PoolManager

_now = time.monotonic
"""Indirection so tests can drive the clock without touching the one `urllib3` itself uses."""

IDLE_CONNECTION_RECYCLE_SECONDS = 90
"""Close a pooled connection that has sat unused for longer than this.

`urllib3` pools from a LIFO queue, so idle time is sharply bimodal rather than spread evenly:
one connection serves nearly everything with sub-second gaps, while any extra connection opened
during a moment of concurrency sinks to the bottom of the stack and is left there indefinitely.
Measured on a traces-plus-metrics workload, 98 of 99 requests went to a single connection. Any
window catches that abandoned tail, because its idle time is unbounded, so the exact value is
not what decides correctness there.

What the value does decide is the session whose only user is the metric exporter, where the one
hot connection has 60 second gaps. Below that interval every export would reconnect, giving up
keep-alive entirely for a fresh handshake each time; 90 seconds keeps the reuse. It stays well
under the idle timeouts of the hops in between, which run to several minutes (AWS NAT gateways
350s, Azure 4 minutes, GCP Cloud NAT 20 minutes). TCP keepalive is the real defence against the
flow being reclaimed, and this window is the backstop for when it does not apply, so it is
cheap to leave it long. For reference `httpx` defaults to 5 seconds and Go's `http.Transport`
to 90.
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
    and which we have no reason to drop. The class is read off the module at call time because
    `urllib3` swaps it out under Pyodide, for an Emscripten connection that talks over `fetch()`
    and so has neither a socket nor any default options.
    """
    defaults = getattr(urllib3_connection.HTTPConnection, 'default_socket_options', None)
    options: list[tuple[int, int, int | bytes]] = [*(defaults or [])]

    def add_if_supported(level: int, name: str, value: int) -> bool:
        # Looked up by name because these constants are platform specific: referring to them
        # directly would not type check on a platform that lacks them.
        option = getattr(socket, name, None)
        if option is None:
            return False
        options.append((level, option, value))
        return True

    if not add_if_supported(socket.SOL_SOCKET, 'SO_KEEPALIVE', 1):
        # Nothing to keep alive, so none of the knobs below mean anything either.
        return options

    # How long a connection may be idle before probing starts. Without this the system default
    # applies, which is two hours on most platforms and so useless against a NAT timeout.
    # Linux (and recent Windows) call it TCP_KEEPIDLE; macOS calls the same thing TCP_KEEPALIVE.
    if not add_if_supported(socket.IPPROTO_TCP, 'TCP_KEEPIDLE', TCP_KEEPALIVE_IDLE_SECONDS):
        add_if_supported(socket.IPPROTO_TCP, 'TCP_KEEPALIVE', TCP_KEEPALIVE_IDLE_SECONDS)
    add_if_supported(socket.IPPROTO_TCP, 'TCP_KEEPINTVL', TCP_KEEPALIVE_INTERVAL_SECONDS)
    add_if_supported(socket.IPPROTO_TCP, 'TCP_KEEPCNT', TCP_KEEPALIVE_FAILED_PROBES)

    return options


class _IdleRecyclingPoolMixin(HTTPConnectionPool):
    """Closes a pooled connection that has sat idle longer than the recycle window.

    The unit that goes stale is one connection, not the session: a session can be busy
    continuously while an individual pooled connection sits unused. That is the normal shape for
    Logfire, where one session carries traces, metrics and logs from different threads, so a
    steady trace stream keeps the session active while the connection that last served a metric
    export waits out the full export interval.

    `urllib3` pools from a LIFO queue, which makes this sharper than steady-state staleness.
    Sequential traffic reuses the connection on top of the stack, so a connection opened during
    a brief overlap is used once and then left at the bottom, idle for as long as the workload
    stays sequential. It is handed back out at the next overlap, which is exactly when a request
    is least able to tolerate a dead socket. Recycling on the way out of the pool is what catches
    that connection before it is used.

    `urllib3` already drops a pooled connection it can see was closed. This extends that to the
    case it cannot see, closing on the way out of the pool and letting `urllib3` reconnect
    lazily, exactly as it does for a connection it detected as dropped.
    """

    def _put_conn(self, conn: Any) -> Any:
        if conn is not None:
            conn._logfire_idle_since = _now()
        return super()._put_conn(conn)

    def _get_conn(self, timeout: float | None = None) -> Any:
        conn = super()._get_conn(timeout)
        # Absent on a connection this pool has never handed back, i.e. a brand new one.
        idle_since = getattr(conn, '_logfire_idle_since', None)
        if idle_since is not None and _now() - idle_since > IDLE_CONNECTION_RECYCLE_SECONDS:
            conn.close()
        return conn


@functools.cache
def _recycling_pool_class(base: type[HTTPConnectionPool]) -> type[HTTPConnectionPool]:
    # Cached so that sessions built repeatedly, such as one per SSE reconnect, share classes.
    return type(f'IdleRecycling{base.__name__}', (_IdleRecyclingPoolMixin, base), {})


def _install_recycling_pools(manager: PoolManager) -> None:
    """Point a pool manager at recycling versions of the pool classes it already uses.

    Derived from whatever the manager has rather than named outright, because the classes vary:
    a SOCKS proxy manager brings its own, and Pyodide swaps in others again. Installed on the
    manager rather than passed through `connection_pool_kw`, because `urllib3` feeds that mapping
    to its pool-key normalizer, which rejects keys it does not know.
    """
    manager.pool_classes_by_scheme = {
        scheme: _recycling_pool_class(cls) for scheme, cls in manager.pool_classes_by_scheme.items()
    }


class LogfireHTTPAdapter(HTTPAdapter):
    """A `requests` adapter that enables TCP keepalive and recycles idle pooled connections."""

    def init_poolmanager(
        self, connections: int, maxsize: int, block: bool = DEFAULT_POOLBLOCK, **pool_kwargs: Any
    ) -> None:
        pool_kwargs.setdefault('socket_options', keepalive_socket_options())
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)
        _install_recycling_pools(self.poolmanager)

    def proxy_manager_for(self, proxy: str, **proxy_kwargs: Any) -> Any:
        # A proxied request goes through a manager of its own, built here rather than by
        # `init_poolmanager`, so the policy has to be applied again as each one appears.
        # `requests` calls this for every proxied request and caches the managers it builds, so
        # one it has already built, and we have already configured, is handed straight back.
        manager = self.proxy_manager.get(proxy)
        if getattr(manager, '_logfire_policy_installed', False):
            return manager
        # `requests` puts a new manager in its cache before handing it back to us, so another
        # thread could pick it up and open a pool before the recycling classes are installed.
        # Building and configuring under a lock, and trusting only a manager that carries the
        # marker, makes those two steps one as far as any other caller can see.
        with _proxy_manager_lock:
            manager = self.proxy_manager.get(proxy)
            if not getattr(manager, '_logfire_policy_installed', False):
                proxy_kwargs.setdefault('socket_options', keepalive_socket_options())
                manager = super().proxy_manager_for(proxy, **proxy_kwargs)
                _install_recycling_pools(manager)
                manager._logfire_policy_installed = True
            return manager


_proxy_manager_lock = threading.Lock()
"""Serializes building proxy managers.

Module level rather than per adapter because `HTTPAdapter` pickles only the attributes it names
itself, so one set in `__init__` would be missing after unpickling. Held only while a manager is
first built, which happens once per proxy, so sharing it costs nothing.
"""


def install_connection_policy(session: Session) -> None:
    """Apply the keepalive and idle recycle policy to a session Logfire owns."""
    adapter = LogfireHTTPAdapter()
    session.mount('http://', adapter)
    session.mount('https://', adapter)
