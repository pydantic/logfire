from __future__ import annotations

import gzip
import inspect
from typing import Any

import pytest
import requests
from opentelemetry.exporter.otlp.proto.common.metrics_encoder import encode_metrics
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.sdk.metrics import Counter, MeterProvider
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    InMemoryMetricReader,
    MetricExportResult,
    MetricsData,
)
from opentelemetry.sdk.metrics.view import Aggregation, DropAggregation
from requests import Response

from logfire._internal.exporters.otlp_proto_http import metric_exporter
from logfire._internal.exporters.otlp_proto_http.metric_exporter import (
    INTENTIONAL_OTEL_DEVIATIONS,
    OWNED_OTEL_ENCODING_DEPENDENCIES,
    UPSTREAM_OTEL_MODULE,
    UPSTREAM_OTEL_VERSION,
    LogfireOTLPMetricExporter,
)


class RecordingSession(requests.Session):
    def __init__(self, response: Response | None = None) -> None:
        super().__init__()
        self.requests: list[dict[str, Any]] = []
        self.closed = False
        self.response = response if response is not None else Response()
        if response is None:
            self.response.status_code = 200

    def post(self, **kwargs: Any) -> Response:  # pyright: ignore[reportIncompatibleMethodOverride]
        self.requests.append(kwargs)
        return self.response

    def close(self) -> None:
        self.closed = True
        super().close()


class FailingSession(requests.Session):
    def post(self, **kwargs: Any) -> Response:  # pyright: ignore[reportIncompatibleMethodOverride]
        raise requests.exceptions.ConnectionError('no connection')


@pytest.fixture
def metrics_data() -> MetricsData:
    reader = InMemoryMetricReader(preferred_temporality={Counter: AggregationTemporality.DELTA})
    provider = MeterProvider(metric_readers=[reader])
    counter = provider.get_meter(__name__).create_counter('owned_metric_exporter_counter')
    counter.add(123, {'route': '/export'})
    collected = reader.get_metrics_data()
    assert collected is not None
    return collected


def test_metric_exporter_serializes_metrics_with_owned_encoder_dependency(metrics_data: MetricsData) -> None:
    session = RecordingSession()
    exporter = LogfireOTLPMetricExporter(
        endpoint='https://logfire.example/v1/metrics',
        session=session,
        headers={'Authorization': 'pylf_v1_test'},
        compression=Compression.NoCompression,
    )

    assert exporter.export(metrics_data) is MetricExportResult.SUCCESS

    assert session.requests[0]['data'] == encode_metrics(metrics_data).SerializeToString()


def test_metric_exporter_preserves_preferred_reader_configuration() -> None:
    preferred_temporality = {Counter: AggregationTemporality.DELTA}
    preferred_aggregation: dict[type, Aggregation] = {Counter: DropAggregation()}

    exporter = LogfireOTLPMetricExporter(
        session=RecordingSession(),
        preferred_temporality=preferred_temporality,
        preferred_aggregation=preferred_aggregation,
    )

    assert exporter._preferred_temporality == preferred_temporality  # pyright: ignore[reportPrivateUsage]
    assert exporter._preferred_aggregation == preferred_aggregation  # pyright: ignore[reportPrivateUsage]


def test_metric_exporter_posts_expected_request_metadata(metrics_data: MetricsData) -> None:
    session = RecordingSession()
    exporter = LogfireOTLPMetricExporter(
        endpoint='https://logfire.example/v1/metrics',
        session=session,
        headers={'User-Agent': 'logfire/test', 'Authorization': 'pylf_v1_test'},
        compression=Compression.Gzip,
        certificate_file='server.pem',
        client_certificate_file='client.pem',
        client_key_file='client-key.pem',
        timeout=12.5,
    )

    assert exporter.export(metrics_data) is MetricExportResult.SUCCESS

    request = session.requests[0]
    assert request['url'] == 'https://logfire.example/v1/metrics'
    assert gzip.decompress(request['data']) == encode_metrics(metrics_data).SerializeToString()
    assert request['verify'] == 'server.pem'
    assert request['timeout'] == 12.5
    assert request['cert'] == ('client.pem', 'client-key.pem')
    assert session.headers['User-Agent'] == 'logfire/test'
    assert session.headers['Authorization'] == 'pylf_v1_test'
    assert session.headers['Content-Type'] == 'application/x-protobuf'
    assert session.headers['Content-Encoding'] == 'gzip'


def test_metric_exporter_maps_non_ok_response_to_failure(metrics_data: MetricsData) -> None:
    response = Response()
    response.status_code = 400
    exporter = LogfireOTLPMetricExporter(session=RecordingSession(response), compression=Compression.NoCompression)

    assert exporter.export(metrics_data) is MetricExportResult.FAILURE


def test_metric_exporter_leaves_request_exceptions_to_quiet_wrapper(metrics_data: MetricsData) -> None:
    exporter = LogfireOTLPMetricExporter(session=FailingSession(), compression=Compression.NoCompression)

    with pytest.raises(requests.exceptions.ConnectionError, match='no connection'):
        exporter.export(metrics_data)


def test_metric_exporter_shutdown_is_state_only_and_force_flush_is_noop(metrics_data: MetricsData) -> None:
    session = RecordingSession()
    exporter = LogfireOTLPMetricExporter(session=session)

    exporter.shutdown()

    assert session.closed is False
    assert exporter.export(metrics_data) is MetricExportResult.FAILURE
    assert session.requests == []
    assert exporter.force_flush() is True


def test_metric_exporter_declares_owned_compatibility_surface() -> None:
    assert UPSTREAM_OTEL_MODULE == 'opentelemetry.exporter.otlp.proto.http.metric_exporter'
    assert UPSTREAM_OTEL_VERSION == '1.41.1'
    assert OWNED_OTEL_ENCODING_DEPENDENCIES == (
        'opentelemetry.exporter.otlp.proto.common.metrics_encoder.encode_metrics',
    )
    assert 'No OpenTelemetry HTTP retry loop' in INTENTIONAL_OTEL_DEVIATIONS[0]


def test_metric_exporter_does_not_copy_opentelemetry_retry_logic() -> None:
    source = inspect.getsource(LogfireOTLPMetricExporter)

    assert '_MAX_RETRYS' not in source
    assert '_is_retryable' not in source
    assert 'ConnectionError' not in source


def test_metric_exporter_encoder_incompatibility_fails_loudly(
    metrics_data: MetricsData, monkeypatch: pytest.MonkeyPatch
) -> None:
    def incompatible_encode_metrics(metrics_data: object) -> object:
        return object()

    monkeypatch.setattr(metric_exporter, 'encode_metrics', incompatible_encode_metrics)
    exporter = LogfireOTLPMetricExporter(session=RecordingSession())

    with pytest.raises(RuntimeError, match='metrics encoder API is incompatible'):
        exporter.export(metrics_data)
