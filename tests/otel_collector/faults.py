from __future__ import annotations

import http.client
import socket
import threading
import time
from collections import deque
from collections.abc import Iterable
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar, Literal, cast
from urllib.parse import urlsplit

FaultAction = int | Literal['drop_response']


class StaleConnectionProxy:
    """A TCP proxy that can blackhole existing connections while keeping new ones healthy."""

    def __init__(self, upstream_host: str, upstream_port: int, *, accept_connect: bool = False) -> None:
        self._upstream = (upstream_host, upstream_port)
        self._accept_connect = accept_connect
        self._listener = socket.socket()
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(('127.0.0.1', 0))
        self._listener.listen()
        self._listener.settimeout(0.1)
        self.endpoint = f'http://127.0.0.1:{self._listener.getsockname()[1]}'
        self._lock = threading.Lock()
        self._next_connection_id = 0
        self._orphan_through = 0
        self._closed = threading.Event()
        self._sockets: list[socket.socket] = []
        self._threads = [threading.Thread(target=self._accept, daemon=True)]
        self._threads[0].start()

    def _accept(self) -> None:
        while not self._closed.is_set():
            try:
                client = self._listener.accept()[0]
            except TimeoutError:
                continue
            except OSError:
                return
            with self._lock:
                self._sockets.append(client)
            # CONNECT headers can arrive over multiple packets. Give the proxy a
            # realistic handshake deadline, then switch to short polling once the
            # tunnel is established so shutdown remains responsive.
            client.settimeout(2 if self._accept_connect else 0.1)
            upstream: socket.socket | None = None
            try:
                initial_upstream_data = self._read_connect_request(client) if self._accept_connect else b''
                upstream = socket.create_connection(self._upstream, timeout=2)
                with self._lock:
                    self._sockets.append(upstream)
                upstream.settimeout(0.1)
                if self._accept_connect:
                    client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                if initial_upstream_data:
                    upstream.sendall(initial_upstream_data)
                client.settimeout(0.1)
            except (OSError, ValueError):
                client.close()
                if upstream is not None:
                    upstream.close()
                continue
            if self._closed.is_set():
                client.close()
                upstream.close()
                return
            with self._lock:
                self._next_connection_id += 1
                connection_id = self._next_connection_id
                threads: list[threading.Thread] = []
                for source, destination in ((client, upstream), (upstream, client)):
                    thread = threading.Thread(
                        target=self._forward, args=(connection_id, source, destination), daemon=True
                    )
                    self._threads.append(thread)
                    threads.append(thread)
            for thread in threads:
                thread.start()

    def _read_connect_request(self, client: socket.socket) -> bytes:
        request = b''
        while b'\r\n\r\n' not in request:
            chunk = client.recv(65536)
            if not chunk:
                raise ValueError('client closed before completing CONNECT request')
            request += chunk
            if len(request) > 65536:
                raise ValueError('CONNECT request headers exceeded 64 KiB')

        headers, initial_upstream_data = request.split(b'\r\n\r\n', 1)
        request_line = headers.split(b'\r\n', 1)[0]
        try:
            method, _authority, version = request_line.split(b' ', 2)
        except ValueError as exc:
            raise ValueError(f'invalid proxy request line: {request_line!r}') from exc
        if method != b'CONNECT' or not version.startswith(b'HTTP/'):
            raise ValueError(f'expected CONNECT request, got: {request_line!r}')

        return initial_upstream_data

    def _forward(self, connection_id: int, source: socket.socket, destination: socket.socket) -> None:
        try:
            while not self._closed.is_set():
                try:
                    data = source.recv(65536)
                except TimeoutError:
                    continue
                if not data:
                    break
                with self._lock:
                    orphaned = connection_id <= self._orphan_through
                if not orphaned:
                    destination.sendall(data)
        except OSError:
            pass
        finally:
            if not self._closed.is_set():
                with closing(source), closing(destination):
                    pass

    def orphan_existing_connections(self) -> None:
        with self._lock:
            self._orphan_through = self._next_connection_id

    @property
    def connection_count(self) -> int:
        with self._lock:
            return self._next_connection_id

    def close(self) -> None:
        self._closed.set()
        self._listener.close()
        with self._lock:
            sockets = list(self._sockets)
        for sock in sockets:
            with closing(sock):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        deadline = time.monotonic() + 2
        self._threads[0].join(timeout=max(0, deadline - time.monotonic()))
        with self._lock:
            threads = list(self._threads)
        for thread in threads[1:]:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        if live_threads := [thread.name for thread in threads if thread.is_alive()]:
            raise AssertionError(f'stale connection proxy threads did not stop: {live_threads}')


class HTTPFaultServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, upstream_endpoint: str, actions: Iterable[FaultAction]) -> None:
        upstream = urlsplit(upstream_endpoint)
        if upstream.scheme != 'http' or upstream.hostname is None or upstream.port is None:
            raise ValueError(f'expected an HTTP upstream with an explicit port, got {upstream_endpoint!r}')
        self._upstream = (upstream.hostname, upstream.port)
        self._upstream_lock = threading.Lock()
        self._condition = threading.Condition()
        self._actions = deque(actions)
        self.attempts = 0
        super().__init__(('127.0.0.1', 0), HTTPFaultRequestHandler)

    def set_upstream(self, upstream_endpoint: str) -> None:
        upstream = urlsplit(upstream_endpoint)
        if upstream.scheme != 'http' or upstream.hostname is None or upstream.port is None:
            raise ValueError(f'expected an HTTP upstream with an explicit port, got {upstream_endpoint!r}')
        with self._upstream_lock:
            self._upstream = (upstream.hostname, upstream.port)

    def upstream(self) -> tuple[str, int]:
        with self._upstream_lock:
            return self._upstream

    def next_action(self) -> FaultAction | None:
        with self._condition:
            self.attempts += 1
            action = self._actions.popleft() if self._actions else None
            self._condition.notify_all()
            return action

    def wait_for_attempts(self, attempts: int, timeout: float = 10) -> None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self.attempts < attempts:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError(f'timed out waiting for {attempts} attempts; observed {self.attempts}')
                self._condition.wait(remaining)


class HTTPFaultRequestHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    hop_by_hop_headers: ClassVar[set[str]] = {
        'connection',
        'content-length',
        'host',
        'keep-alive',
        'proxy-authenticate',
        'proxy-authorization',
        'te',
        'trailer',
        'transfer-encoding',
        'upgrade',
    }

    def do_POST(self) -> None:
        server = cast(HTTPFaultServer, self.server)
        body = self.rfile.read(int(self.headers['Content-Length']))
        action = server.next_action()

        if isinstance(action, int):
            self.send_response(action)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return

        headers = {key: value for key, value in self.headers.items() if key.lower() not in self.hop_by_hop_headers}
        upstream = http.client.HTTPConnection(*server.upstream(), timeout=2)
        try:
            try:
                upstream.request('POST', self.path, body=body, headers=headers)
                response = upstream.getresponse()
                response_body = response.read()
                response_headers = response.getheaders()
            except (OSError, http.client.HTTPException):
                self._drop_connection()
                return
        finally:
            upstream.close()

        if action == 'drop_response':
            self._drop_connection()
            return

        self.send_response(response.status)
        for key, value in response_headers:
            if key.lower() not in self.hop_by_hop_headers:
                self.send_header(key, value)
        self.send_header('Content-Length', str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def _drop_connection(self) -> None:
        self.close_connection = True
        with closing(self.connection):
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def log_message(self, format: str, *args: Any) -> None:
        pass


class HTTPFaultProxy:
    """A programmable reverse proxy for deterministic response and disconnect faults."""

    def __init__(self, upstream_endpoint: str, actions: Iterable[FaultAction]) -> None:
        self._server = HTTPFaultServer(upstream_endpoint, actions)
        self.endpoint = f'http://127.0.0.1:{self._server.server_address[1]}'
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def attempts(self) -> int:
        return self._server.attempts

    def wait_for_attempts(self, attempts: int, timeout: float = 10) -> None:
        self._server.wait_for_attempts(attempts, timeout)

    def set_upstream(self, upstream_endpoint: str) -> None:
        self._server.set_upstream(upstream_endpoint)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
