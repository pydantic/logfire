from requests import Session
from requests.adapters import HTTPAdapter
from typing import Any
from urllib3.connectionpool import HTTPConnectionPool

IDLE_CONNECTION_RECYCLE_SECONDS: int
TCP_KEEPALIVE_IDLE_SECONDS: int
TCP_KEEPALIVE_INTERVAL_SECONDS: int
TCP_KEEPALIVE_FAILED_PROBES: int

def keepalive_socket_options() -> list[tuple[int, int, int | bytes]]:
    """`urllib3`'s default socket options plus TCP keepalive.

    Building on `HTTPConnection.default_socket_options` keeps `TCP_NODELAY`, which `urllib3` sets
    and which we have no reason to drop. The class is read off the module at call time because
    `urllib3` swaps it out under Pyodide, for an Emscripten connection that talks over `fetch()`
    and so has neither a socket nor any default options.
    """

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

class LogfireHTTPAdapter(HTTPAdapter):
    """A `requests` adapter that enables TCP keepalive and recycles idle pooled connections."""
    def init_poolmanager(self, connections: int, maxsize: int, block: bool = ..., **pool_kwargs: Any) -> None: ...
    def proxy_manager_for(self, proxy: str, **proxy_kwargs: Any) -> Any: ...

def install_connection_policy(session: Session) -> None:
    """Apply the keepalive and idle recycle policy to a session Logfire owns."""
