from __future__ import annotations

import gzip
import json
import os
import shutil
import socket
import ssl
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest, ExportLogsServiceResponse
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from tests.otel_collector.faults import HTTPFaultProxy

COLLECTOR_IMAGE = (
    'otel/opentelemetry-collector:0.159.0@sha256:7725a7a10c87d8853208bdd4bb3439ad3c0d7b32b4292b9300ac07c8daba14a2'
)


class CaptureStore:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self.traces: list[ExportTraceServiceRequest] = []
        self.metrics: list[ExportMetricsServiceRequest] = []
        self.logs: list[ExportLogsServiceRequest] = []

    def add(self, request: Message) -> None:
        with self._condition:
            if isinstance(request, ExportTraceServiceRequest):
                self.traces.append(request)
            elif isinstance(request, ExportMetricsServiceRequest):
                self.metrics.append(request)
            elif isinstance(request, ExportLogsServiceRequest):
                self.logs.append(request)
            else:  # pragma: no cover - request types are fixed by CaptureRequestHandler
                raise TypeError(f'unsupported request type: {type(request)!r}')
            self._condition.notify_all()

    def wait_until(self, predicate: Callable[[CaptureStore], bool], description: str, timeout: float = 10) -> None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while not predicate(self):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError(f'timed out waiting for {description}')
                self._condition.wait(remaining)

    def dump(self, path: Path) -> None:
        output = {
            'traces': [MessageToDict(request, preserving_proto_field_name=True) for request in self.traces],
            'metrics': [MessageToDict(request, preserving_proto_field_name=True) for request in self.metrics],
            'logs': [MessageToDict(request, preserving_proto_field_name=True) for request in self.logs],
        }
        path.write_text(json.dumps(output, indent=2, sort_keys=True))


class CaptureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(('0.0.0.0', 0), CaptureRequestHandler)
        self.store = CaptureStore()


class CaptureRequestHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    request_types: ClassVar[dict[str, tuple[type[Message], type[Message]]]] = {
        '/v1/traces': (ExportTraceServiceRequest, ExportTraceServiceResponse),
        '/v1/metrics': (ExportMetricsServiceRequest, ExportMetricsServiceResponse),
        '/v1/logs': (ExportLogsServiceRequest, ExportLogsServiceResponse),
    }

    def do_POST(self) -> None:
        try:
            request_type, response_type = self.request_types[self.path]
        except KeyError:
            self.send_error(404)
            return

        body = self.rfile.read(int(self.headers['Content-Length']))
        if self.headers.get('Content-Encoding') == 'gzip':
            body = gzip.decompress(body)

        request = request_type()
        request.ParseFromString(body)
        cast(CaptureServer, self.server).store.add(request)

        response = response_type().SerializeToString()
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-protobuf')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        try:
            self.wfile.write(response)
        except BrokenPipeError:
            # The capture is the acceptance boundary. A deliberately faulted caller may stop
            # waiting for the acknowledgement after the request has already arrived.
            pass

    def log_message(self, format: str, *args: Any) -> None:
        pass


class CollectorHarness:
    def __init__(
        self,
        gateway: HTTPFaultProxy,
        tls_endpoint: str,
        certificate_path: Path,
        capture: CaptureStore,
        container_name: str,
        artifacts_dir: Path,
        docker_command: list[str],
        host: str,
        http_port: int,
        tls_host: str,
        tls_port: int,
    ) -> None:
        self._gateway = gateway
        self.endpoint = gateway.endpoint
        self.tls_endpoint = tls_endpoint
        self.certificate_path = certificate_path
        self.capture = capture
        self.container_name = container_name
        self.artifacts_dir = artifacts_dir
        self._docker_command = docker_command
        self._restart_count = 0
        self.host = host
        self.http_port = http_port
        self.tls_host = tls_host
        self.tls_port = tls_port

    def stop(self) -> None:
        subprocess.run(
            ['docker', 'stop', '--time', '0', self.container_name], capture_output=True, text=True, check=True
        )

    def restart(self) -> None:
        self._restart_count += 1
        logs = subprocess.run(['docker', 'logs', self.container_name], capture_output=True, text=True)
        (self.artifacts_dir / f'collector-before-restart-{self._restart_count}.log').write_text(
            logs.stdout + logs.stderr
        )
        subprocess.run(['docker', 'rm', '--force', self.container_name], capture_output=True, text=True, check=True)
        run = subprocess.run(self._docker_command, capture_output=True, text=True)
        if run.returncode != 0:
            raise RuntimeError(f'failed to restart Collector:\n{run.stdout}\n{run.stderr}')

        self.host, self.http_port, self.tls_host, self.tls_port = _collector_addresses(self.container_name)
        _wait_for_port(self.host, self.http_port, timeout=10, container_name=self.container_name)
        _wait_for_tls_port(
            self.tls_host,
            self.tls_port,
            certificate_path=self.certificate_path,
            timeout=10,
            container_name=self.container_name,
        )
        self._gateway.set_upstream(f'http://{self.host}:{self.http_port}')
        self.tls_endpoint = f'https://{self.tls_host}:{self.tls_port}'


@pytest.fixture(scope='session', autouse=True)
def require_collector_tests_enabled() -> None:
    if os.getenv('LOGFIRE_OTEL_COLLECTOR_TESTS') != '1':
        pytest.skip('set LOGFIRE_OTEL_COLLECTOR_TESTS=1 to run tests that require Docker')


def _wait_for_port(host: str, port: int, *, timeout: float, container_name: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            state = subprocess.run(
                ['docker', 'inspect', '--format', '{{.State.Running}}', container_name],
                capture_output=True,
                text=True,
            )
            if state.returncode != 0 or state.stdout.strip() != 'true':
                logs = subprocess.run(['docker', 'logs', container_name], capture_output=True, text=True)
                raise RuntimeError(f'Collector exited before becoming ready:\n{logs.stdout}\n{logs.stderr}')
            time.sleep(0.05)
    raise TimeoutError(f'Collector did not listen on {host}:{port} within {timeout}s')


def _wait_for_tls_port(host: str, port: int, *, certificate_path: Path, timeout: float, container_name: str) -> None:
    context = ssl.create_default_context(cafile=certificate_path)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2) as connection:
                with context.wrap_socket(connection, server_hostname=host):
                    return
        except OSError:
            state = subprocess.run(
                ['docker', 'inspect', '--format', '{{.State.Running}}', container_name],
                capture_output=True,
                text=True,
            )
            if state.returncode != 0 or state.stdout.strip() != 'true':
                logs = subprocess.run(['docker', 'logs', container_name], capture_output=True, text=True)
                raise RuntimeError(f'Collector exited before becoming ready:\n{logs.stdout}\n{logs.stderr}')
            time.sleep(0.05)
    raise TimeoutError(f'Collector did not negotiate TLS on {host}:{port} within {timeout}s')


def _collector_addresses(container_name: str) -> tuple[str, int, str, int]:
    http_port_result = subprocess.run(
        ['docker', 'port', container_name, '4318/tcp'], capture_output=True, text=True, check=True
    )
    tls_port_result = subprocess.run(
        ['docker', 'port', container_name, '4319/tcp'], capture_output=True, text=True, check=True
    )
    host, http_port_text = http_port_result.stdout.strip().rsplit(':', 1)
    tls_host, tls_port_text = tls_port_result.stdout.strip().rsplit(':', 1)
    return host, int(http_port_text), tls_host, int(tls_port_text)


@pytest.fixture(scope='session')
def collector_harness(tmp_path_factory: pytest.TempPathFactory) -> Iterator[CollectorHarness]:
    if shutil.which('docker') is None:
        pytest.fail('Docker is required when LOGFIRE_OTEL_COLLECTOR_TESTS=1')
    if shutil.which('openssl') is None:
        pytest.fail('OpenSSL is required when LOGFIRE_OTEL_COLLECTOR_TESTS=1')

    capture_server = CaptureServer()
    capture_thread = threading.Thread(target=capture_server.serve_forever, daemon=True)
    capture_thread.start()

    artifacts_env = os.getenv('LOGFIRE_OTEL_COLLECTOR_ARTIFACTS')
    artifacts_dir = Path(artifacts_env) if artifacts_env else tmp_path_factory.mktemp('otel-collector-artifacts')
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    config_path = artifacts_dir / 'collector.yaml'
    certificate_path = artifacts_dir / 'certificate.pem'
    key_path = artifacts_dir / 'key.pem'
    container_name = f'logfire-otel-conformance-{uuid.uuid4().hex}'
    gateway: HTTPFaultProxy | None = None
    try:
        certificate = subprocess.run(
            [
                'openssl',
                'req',
                '-x509',
                '-newkey',
                'rsa:2048',
                '-nodes',
                '-keyout',
                str(key_path),
                '-out',
                str(certificate_path),
                '-days',
                '1',
                '-subj',
                '/CN=localhost',
                '-addext',
                'subjectAltName=DNS:localhost,IP:127.0.0.1',
            ],
            capture_output=True,
            text=True,
        )
        if certificate.returncode != 0:
            pytest.fail(f'failed to generate Collector certificate:\n{certificate.stdout}\n{certificate.stderr}')
        key_path.chmod(0o644)
        capture_port = capture_server.server_address[1]
        config_path.write_text(
            f"""receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
  otlp/tls:
    protocols:
      http:
        endpoint: 0.0.0.0:4319
        tls:
          cert_file: /test-artifacts/certificate.pem
          key_file: /test-artifacts/key.pem

exporters:
  otlp_http/capture:
    endpoint: http://host.docker.internal:{capture_port}
    compression: none
    sending_queue:
      enabled: false
    retry_on_failure:
      enabled: false

service:
  pipelines:
    traces:
      receivers: [otlp, otlp/tls]
      exporters: [otlp_http/capture]
    metrics:
      receivers: [otlp, otlp/tls]
      exporters: [otlp_http/capture]
    logs:
      receivers: [otlp, otlp/tls]
      exporters: [otlp_http/capture]
"""
        )

        docker_command = [
            'docker',
            'run',
            '--detach',
            '--name',
            container_name,
            '--add-host',
            'host.docker.internal:host-gateway',
            '--publish',
            '127.0.0.1::4318',
            '--publish',
            '127.0.0.1::4319',
            '--volume',
            f'{config_path.resolve()}:/etc/otelcol/config.yaml:ro',
            '--volume',
            f'{certificate_path.resolve()}:/test-artifacts/certificate.pem:ro',
            '--volume',
            f'{key_path.resolve()}:/test-artifacts/key.pem:ro',
            COLLECTOR_IMAGE,
            '--config=/etc/otelcol/config.yaml',
        ]
        run = subprocess.run(docker_command, capture_output=True, text=True)
        if run.returncode != 0:
            pytest.fail(f'failed to start Collector:\n{run.stdout}\n{run.stderr}')

        host, http_port, tls_host, tls_port = _collector_addresses(container_name)
        _wait_for_port(host, http_port, timeout=10, container_name=container_name)
        _wait_for_tls_port(
            tls_host,
            tls_port,
            certificate_path=certificate_path,
            timeout=10,
            container_name=container_name,
        )
        gateway = HTTPFaultProxy(f'http://{host}:{http_port}', [])
        yield CollectorHarness(
            gateway=gateway,
            tls_endpoint=f'https://{tls_host}:{tls_port}',
            certificate_path=certificate_path,
            capture=capture_server.store,
            container_name=container_name,
            artifacts_dir=artifacts_dir,
            docker_command=docker_command,
            host=host,
            http_port=http_port,
            tls_host=tls_host,
            tls_port=tls_port,
        )
    finally:
        try:
            logs = subprocess.run(['docker', 'logs', container_name], capture_output=True, text=True)
            if logs.returncode == 0:
                (artifacts_dir / 'collector.log').write_text(logs.stdout + logs.stderr)
            capture_server.store.dump(artifacts_dir / 'captured-otlp.json')
        finally:
            try:
                if gateway is not None:
                    gateway.close()
            finally:
                try:
                    subprocess.run(['docker', 'rm', '--force', container_name], capture_output=True)
                finally:
                    try:
                        key_path.unlink(missing_ok=True)
                    finally:
                        capture_server.shutdown()
                        capture_server.server_close()
                        capture_thread.join(timeout=5)
