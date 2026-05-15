from __future__ import annotations

import gzip
import zlib
from unittest.mock import Mock

import pytest
import requests
from opentelemetry.exporter.otlp.proto.http import Compression

from logfire._internal.exporters.otlp_proto_http._common import (
    DEFAULT_TIMEOUT,
    OTLP_HTTP_HEADERS,
    SIGNAL_ENVIRONMENT_VARIABLES,
    SignalName,
    apply_session_headers,
    compress_serialized_data,
    post_serialized_data,
    resolve_certificate_file,
    resolve_client_cert,
    resolve_timeout,
)


@pytest.fixture(autouse=True)
def clear_effective_otlp_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    env_var_names = {
        'OTEL_EXPORTER_OTLP_TIMEOUT',
        'OTEL_EXPORTER_OTLP_CERTIFICATE',
        'OTEL_EXPORTER_OTLP_CLIENT_CERTIFICATE',
        'OTEL_EXPORTER_OTLP_CLIENT_KEY',
    }
    for env_vars in SIGNAL_ENVIRONMENT_VARIABLES.values():
        env_var_names.update(
            {
                env_vars.timeout,
                env_vars.certificate,
                env_vars.client_certificate,
                env_vars.client_key,
            }
        )
    for env_var_name in env_var_names:
        monkeypatch.delenv(env_var_name, raising=False)


def test_apply_session_headers_preserves_logfire_headers_over_otlp_defaults() -> None:
    session = requests.Session()

    apply_session_headers(
        session,
        {'User-Agent': 'logfire/test', 'Authorization': 'pylf_v1_test'},
        Compression.Gzip,
    )

    assert session.headers['User-Agent'] == 'logfire/test'
    assert session.headers['Authorization'] == 'pylf_v1_test'
    assert session.headers['Content-Type'] == OTLP_HTTP_HEADERS['Content-Type']
    assert session.headers['Content-Encoding'] == 'gzip'


def test_apply_session_headers_omits_content_encoding_without_compression() -> None:
    session = requests.Session()

    apply_session_headers(session, None, Compression.NoCompression)

    assert session.headers['Content-Type'] == 'application/x-protobuf'
    assert 'Content-Encoding' not in session.headers


def test_compress_serialized_data() -> None:
    payload = b'payload'

    assert gzip.decompress(compress_serialized_data(payload, Compression.Gzip)) == payload
    assert zlib.decompress(compress_serialized_data(payload, Compression.Deflate)) == payload
    assert compress_serialized_data(payload, Compression.NoCompression) == payload


@pytest.mark.parametrize('signal', ['traces', 'metrics', 'logs'])
def test_timeout_resolution_uses_exact_effective_env_vars(signal: SignalName, monkeypatch: pytest.MonkeyPatch) -> None:
    signal_timeout = SIGNAL_ENVIRONMENT_VARIABLES[signal].timeout
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_TIMEOUT', '11')

    assert resolve_timeout(signal, None) == 11

    monkeypatch.setenv(signal_timeout, '12')
    assert resolve_timeout(signal, None) == 12
    assert resolve_timeout(signal, 13) == 13


@pytest.mark.parametrize('signal', ['traces', 'metrics', 'logs'])
def test_timeout_defaults_to_ten_seconds(signal: SignalName) -> None:
    assert resolve_timeout(signal, None) == DEFAULT_TIMEOUT


@pytest.mark.parametrize('signal', ['traces', 'metrics', 'logs'])
def test_certificate_resolution_uses_exact_effective_env_vars(
    signal: SignalName, monkeypatch: pytest.MonkeyPatch
) -> None:
    signal_certificate = SIGNAL_ENVIRONMENT_VARIABLES[signal].certificate
    assert resolve_certificate_file(signal, None) is True

    monkeypatch.setenv('OTEL_EXPORTER_OTLP_CERTIFICATE', 'generic.pem')
    assert resolve_certificate_file(signal, None) == 'generic.pem'

    monkeypatch.setenv(signal_certificate, 'signal.pem')
    assert resolve_certificate_file(signal, None) == 'signal.pem'
    assert resolve_certificate_file(signal, 'explicit.pem') == 'explicit.pem'


@pytest.mark.parametrize('signal', ['traces', 'metrics', 'logs'])
def test_client_cert_resolution_uses_exact_effective_env_vars(
    signal: SignalName, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_vars = SIGNAL_ENVIRONMENT_VARIABLES[signal]
    assert resolve_client_cert(signal, None, None) is None

    monkeypatch.setenv('OTEL_EXPORTER_OTLP_CLIENT_CERTIFICATE', 'generic-cert.pem')
    assert resolve_client_cert(signal, None, None) == 'generic-cert.pem'

    monkeypatch.setenv('OTEL_EXPORTER_OTLP_CLIENT_KEY', 'generic-key.pem')
    assert resolve_client_cert(signal, None, None) == ('generic-cert.pem', 'generic-key.pem')

    monkeypatch.setenv(env_vars.client_certificate, 'signal-cert.pem')
    monkeypatch.setenv(env_vars.client_key, 'signal-key.pem')
    assert resolve_client_cert(signal, None, None) == ('signal-cert.pem', 'signal-key.pem')
    assert resolve_client_cert(signal, 'explicit-cert.pem', 'explicit-key.pem') == (
        'explicit-cert.pem',
        'explicit-key.pem',
    )


def test_generic_endpoint_header_and_compression_env_vars_do_not_affect_common_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'https://otel.example')
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_HEADERS', 'Authorization=otel')
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_COMPRESSION', 'deflate')

    session = requests.Session()
    apply_session_headers(session, {'Authorization': 'logfire'}, Compression.Gzip)

    assert session.headers['Authorization'] == 'logfire'
    assert session.headers['Content-Encoding'] == 'gzip'


def test_post_serialized_data_uses_supplied_request_metadata() -> None:
    session = Mock(spec=requests.Session)
    response = requests.Response()
    session.post.return_value = response

    assert (
        post_serialized_data(
            session,
            'https://example.com/v1/traces',
            b'payload',
            compression=Compression.Deflate,
            certificate_file='cert.pem',
            timeout=12.5,
            client_cert=('client.pem', 'key.pem'),
        )
        is response
    )

    session.post.assert_called_once()
    _, kwargs = session.post.call_args
    assert kwargs == {
        'url': 'https://example.com/v1/traces',
        'data': zlib.compress(b'payload'),
        'verify': 'cert.pem',
        'timeout': 12.5,
        'cert': ('client.pem', 'key.pem'),
    }


def test_common_environment_mapping_is_exact() -> None:
    mapped_env_vars: set[str] = set()
    for env_vars in SIGNAL_ENVIRONMENT_VARIABLES.values():
        mapped_env_vars.update(
            {
                env_vars.timeout,
                env_vars.certificate,
                env_vars.client_certificate,
                env_vars.client_key,
            }
        )

    assert mapped_env_vars == {
        'OTEL_EXPORTER_OTLP_TRACES_TIMEOUT',
        'OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE',
        'OTEL_EXPORTER_OTLP_TRACES_CLIENT_CERTIFICATE',
        'OTEL_EXPORTER_OTLP_TRACES_CLIENT_KEY',
        'OTEL_EXPORTER_OTLP_METRICS_TIMEOUT',
        'OTEL_EXPORTER_OTLP_METRICS_CERTIFICATE',
        'OTEL_EXPORTER_OTLP_METRICS_CLIENT_CERTIFICATE',
        'OTEL_EXPORTER_OTLP_METRICS_CLIENT_KEY',
        'OTEL_EXPORTER_OTLP_LOGS_TIMEOUT',
        'OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE',
        'OTEL_EXPORTER_OTLP_LOGS_CLIENT_CERTIFICATE',
        'OTEL_EXPORTER_OTLP_LOGS_CLIENT_KEY',
    }
