from __future__ import annotations

from typing import Any

import requests
from opentelemetry.exporter.otlp.proto.common.metrics_encoder import encode_metrics
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    MetricExporter,
    MetricExportResult,
    MetricsData,
)
from opentelemetry.sdk.metrics.view import Aggregation

from ._common import (
    ClientCert,
    apply_session_headers,
    post_serialized_data,
    resolve_certificate_file,
    resolve_client_cert,
    resolve_timeout,
)

UPSTREAM_OTEL_MODULE = 'opentelemetry.exporter.otlp.proto.http.metric_exporter'
UPSTREAM_OTEL_VERSION = '1.41.1'
OWNED_OTEL_ENCODING_DEPENDENCIES = ('opentelemetry.exporter.otlp.proto.common.metrics_encoder.encode_metrics',)
INTENTIONAL_OTEL_DEVIATIONS = (
    'No OpenTelemetry HTTP retry loop; Logfire request retry remains in OTLPExporterHttpSession/DiskRetryer.',
    'No OpenTelemetry private credential-provider or session loading.',
    'No generic OTLP endpoint, header, or compression environment handling in the Logfire token path.',
    'Exporter shutdown is state-only and does not close the supplied shared session.',
    'No OpenTelemetry max_export_batch_size split behavior; it is outside the Logfire token-path preservation target.',
)

DEFAULT_ENDPOINT = 'http://localhost:4318/v1/metrics'


class LogfireOTLPMetricExporter(MetricExporter):
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
        preferred_temporality: dict[type, AggregationTemporality] | None = None,
        preferred_aggregation: dict[type, Aggregation] | None = None,
    ) -> None:
        super().__init__(
            preferred_temporality=preferred_temporality,
            preferred_aggregation=preferred_aggregation,
        )
        self._endpoint = endpoint
        self._headers = dict(headers or {})
        self._timeout = resolve_timeout('metrics', timeout)
        self._certificate_file = resolve_certificate_file('metrics', certificate_file)
        self._client_cert: ClientCert = resolve_client_cert('metrics', client_certificate_file, client_key_file)
        self._compression = compression
        self._session = session
        self._shutdown = False

        apply_session_headers(self._session, self._headers, self._compression)

    def export(
        self,
        metrics_data: MetricsData,
        timeout_millis: float = 10_000,
        **kwargs: Any,
    ) -> MetricExportResult:
        if self._shutdown:
            return MetricExportResult.FAILURE

        response = self._export(self._serialize_metrics(metrics_data))
        if response.ok:
            return MetricExportResult.SUCCESS
        return MetricExportResult.FAILURE

    def _serialize_metrics(self, metrics_data: MetricsData) -> bytes:
        try:
            return encode_metrics(metrics_data).SerializeToString()
        except Exception as exc:
            raise RuntimeError(
                'OpenTelemetry metrics encoder API is incompatible with LogfireOTLPMetricExporter. '
                'Expected encode_metrics(...) to return a protobuf message with SerializeToString().'
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

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
        self._shutdown = True

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True
