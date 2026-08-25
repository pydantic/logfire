from __future__ import annotations

import socket
import time

from tests.otel_collector.faults import StaleConnectionProxy


def test_connect_proxy_allows_headers_to_arrive_in_multiple_packets() -> None:
    with socket.socket() as upstream:
        upstream.bind(('127.0.0.1', 0))
        upstream.listen()
        proxy = StaleConnectionProxy('127.0.0.1', upstream.getsockname()[1], accept_connect=True)
        try:
            with socket.create_connection(('127.0.0.1', int(proxy.endpoint.rsplit(':', 1)[1]))) as client:
                client.settimeout(1)
                client.sendall(b'CONNECT localhost:443 HTTP/1.1\r\nHost: local')
                time.sleep(0.15)
                client.sendall(b'host:443\r\n\r\n')

                assert client.recv(4096).startswith(b'HTTP/1.1 200 Connection Established\r\n')
        finally:
            proxy.close()
