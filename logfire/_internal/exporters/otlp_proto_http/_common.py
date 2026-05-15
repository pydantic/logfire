from __future__ import annotations

import gzip
import os
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from typing import Literal, Union

import requests
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.sdk.environment_variables import (
    OTEL_EXPORTER_OTLP_CERTIFICATE,
    OTEL_EXPORTER_OTLP_CLIENT_CERTIFICATE,
    OTEL_EXPORTER_OTLP_CLIENT_KEY,
    OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE,
    OTEL_EXPORTER_OTLP_LOGS_CLIENT_CERTIFICATE,
    OTEL_EXPORTER_OTLP_LOGS_CLIENT_KEY,
    OTEL_EXPORTER_OTLP_LOGS_TIMEOUT,
    OTEL_EXPORTER_OTLP_METRICS_CERTIFICATE,
    OTEL_EXPORTER_OTLP_METRICS_CLIENT_CERTIFICATE,
    OTEL_EXPORTER_OTLP_METRICS_CLIENT_KEY,
    OTEL_EXPORTER_OTLP_METRICS_TIMEOUT,
    OTEL_EXPORTER_OTLP_TIMEOUT,
    OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE,
    OTEL_EXPORTER_OTLP_TRACES_CLIENT_CERTIFICATE,
    OTEL_EXPORTER_OTLP_TRACES_CLIENT_KEY,
    OTEL_EXPORTER_OTLP_TRACES_TIMEOUT,
)

SignalName = Literal['traces', 'metrics', 'logs']
ClientCert = Union[str, tuple[str, str], None]

DEFAULT_TIMEOUT = 10.0
OTLP_HTTP_HEADERS: Mapping[str, str] = {'Content-Type': 'application/x-protobuf'}


@dataclass(frozen=True)
class SignalEnvironmentVariables:
    timeout: str
    certificate: str
    client_certificate: str
    client_key: str


SIGNAL_ENVIRONMENT_VARIABLES: Mapping[SignalName, SignalEnvironmentVariables] = {
    'traces': SignalEnvironmentVariables(
        timeout=OTEL_EXPORTER_OTLP_TRACES_TIMEOUT,
        certificate=OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE,
        client_certificate=OTEL_EXPORTER_OTLP_TRACES_CLIENT_CERTIFICATE,
        client_key=OTEL_EXPORTER_OTLP_TRACES_CLIENT_KEY,
    ),
    'metrics': SignalEnvironmentVariables(
        timeout=OTEL_EXPORTER_OTLP_METRICS_TIMEOUT,
        certificate=OTEL_EXPORTER_OTLP_METRICS_CERTIFICATE,
        client_certificate=OTEL_EXPORTER_OTLP_METRICS_CLIENT_CERTIFICATE,
        client_key=OTEL_EXPORTER_OTLP_METRICS_CLIENT_KEY,
    ),
    'logs': SignalEnvironmentVariables(
        timeout=OTEL_EXPORTER_OTLP_LOGS_TIMEOUT,
        certificate=OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE,
        client_certificate=OTEL_EXPORTER_OTLP_LOGS_CLIENT_CERTIFICATE,
        client_key=OTEL_EXPORTER_OTLP_LOGS_CLIENT_KEY,
    ),
}


def resolve_timeout(signal: SignalName, explicit_timeout: float | None) -> float:
    if explicit_timeout is not None:
        return explicit_timeout

    signal_env = SIGNAL_ENVIRONMENT_VARIABLES[signal].timeout
    return float(os.environ.get(signal_env, os.environ.get(OTEL_EXPORTER_OTLP_TIMEOUT, DEFAULT_TIMEOUT)))


def resolve_certificate_file(signal: SignalName, explicit_certificate_file: str | None) -> str | bool:
    if explicit_certificate_file:
        return explicit_certificate_file

    signal_env = SIGNAL_ENVIRONMENT_VARIABLES[signal].certificate
    if signal_env in os.environ:
        return os.environ[signal_env]
    return os.environ.get(OTEL_EXPORTER_OTLP_CERTIFICATE, True)


def resolve_client_cert(
    signal: SignalName,
    explicit_client_certificate_file: str | None,
    explicit_client_key_file: str | None,
) -> ClientCert:
    env_vars = SIGNAL_ENVIRONMENT_VARIABLES[signal]
    client_certificate_file = explicit_client_certificate_file or os.environ.get(
        env_vars.client_certificate,
        os.environ.get(OTEL_EXPORTER_OTLP_CLIENT_CERTIFICATE),
    )
    client_key_file = explicit_client_key_file or os.environ.get(
        env_vars.client_key,
        os.environ.get(OTEL_EXPORTER_OTLP_CLIENT_KEY),
    )
    if client_certificate_file and client_key_file:
        return client_certificate_file, client_key_file
    return client_certificate_file


def apply_session_headers(
    session: requests.Session,
    headers: Mapping[str, str] | None,
    compression: Compression,
) -> None:
    if headers:
        session.headers.update(headers)
    session.headers.update(OTLP_HTTP_HEADERS)
    if headers:
        session.headers.update(headers)
    if compression is not Compression.NoCompression:
        session.headers.update({'Content-Encoding': compression.value})


def compress_serialized_data(serialized_data: bytes, compression: Compression) -> bytes:
    if compression == Compression.Gzip:
        gzip_data = BytesIO()
        with gzip.GzipFile(fileobj=gzip_data, mode='w') as gzip_stream:
            gzip_stream.write(serialized_data)
        return gzip_data.getvalue()
    if compression == Compression.Deflate:
        return zlib.compress(serialized_data)
    return serialized_data


def post_serialized_data(
    session: requests.Session,
    endpoint: str,
    serialized_data: bytes,
    *,
    compression: Compression,
    certificate_file: str | bool,
    timeout: float,
    client_cert: ClientCert,
) -> requests.Response:
    return session.post(
        url=endpoint,
        data=compress_serialized_data(serialized_data, compression),
        verify=certificate_file,
        timeout=timeout,
        cert=client_cert,
    )
