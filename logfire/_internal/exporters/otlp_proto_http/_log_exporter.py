from __future__ import annotations

from collections.abc import Sequence

import requests
from opentelemetry.exporter.otlp.proto.common._log_encoder import encode_logs
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk._logs.export import LogRecordExporter, LogRecordExportResult

from ._common import (
    ClientCert,
    apply_session_headers,
    post_serialized_data,
    resolve_certificate_file,
    resolve_client_cert,
    resolve_timeout,
)

UPSTREAM_OTEL_MODULE = 'opentelemetry.exporter.otlp.proto.http._log_exporter'
UPSTREAM_OTEL_VERSION = '1.41.1'
OWNED_OTEL_ENCODING_DEPENDENCIES = ('opentelemetry.exporter.otlp.proto.common._log_encoder.encode_logs',)
INTENTIONAL_OTEL_DEVIATIONS = (
    'No OpenTelemetry HTTP retry loop; Logfire request retry remains in OTLPExporterHttpSession/DiskRetryer.',
    'No OpenTelemetry private credential-provider or session loading.',
    'No generic OTLP endpoint, header, or compression environment handling in the Logfire token path.',
    'Exporter shutdown is state-only and does not close the supplied shared session.',
)

DEFAULT_ENDPOINT = 'http://localhost:4318/v1/logs'


class LogfireOTLPLogExporter(LogRecordExporter):
    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        *,
        certificate_file: str | None = None,
        client_key_file: str | None = None,
        client_certificate_file: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        compression: Compression = Compression.Gzip,
        session: requests.Session,
    ) -> None:
        self._endpoint = endpoint
        self._headers = dict(headers or {})
        self._timeout = resolve_timeout('logs', timeout)
        self._certificate_file = resolve_certificate_file('logs', certificate_file)
        self._client_cert: ClientCert = resolve_client_cert('logs', client_certificate_file, client_key_file)
        self._compression = compression
        self._session = session
        self._shutdown = False

        apply_session_headers(self._session, self._headers, self._compression)

    def export(self, batch: Sequence[ReadableLogRecord]) -> LogRecordExportResult:
        if self._shutdown:
            return LogRecordExportResult.FAILURE

        response = self._export(self._serialize_logs(batch))
        if response.ok:
            return LogRecordExportResult.SUCCESS
        return LogRecordExportResult.FAILURE

    def _serialize_logs(self, batch: Sequence[ReadableLogRecord]) -> bytes:
        try:
            return encode_logs(batch).SerializeToString()
        except Exception as exc:
            raise RuntimeError(
                'OpenTelemetry log encoder API is incompatible with LogfireOTLPLogExporter. '
                'Expected encode_logs(...) to return a protobuf message with SerializeToString().'
            ) from exc

    def _export(self, serialized_data: bytes) -> requests.Response:
        return post_serialized_data(
            self._session,
            self._endpoint,
            serialized_data,
            compression=self._compression,
            certificate_file=self._certificate_file,
            timeout=self._timeout,
            client_cert=self._client_cert,
        )

    def shutdown(self) -> None:
        self._shutdown = True

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True
