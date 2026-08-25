from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

import pytest
import requests
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue

from logfire._internal.exporters.otlp import OTLPExporterHttpSession, SuppressedConnectionError
from tests.otel_collector.conftest import CaptureStore, CollectorHarness
from tests.otel_collector.faults import HTTPFaultProxy

pytestmark = pytest.mark.otel_collector

Signal = Literal['traces', 'metrics', 'logs']


@dataclass(frozen=True)
class OTLPRequest:
    signal: Signal
    path: str
    body: bytes
    event_ids: frozenset[str]


def _attribute(event_id: str) -> KeyValue:
    return KeyValue(key='test.event_id', value=AnyValue(string_value=event_id))


def _requests(run_id: str, count: int) -> list[OTLPRequest]:
    event_ids = frozenset(f'{run_id}:{index}' for index in range(count))

    traces = ExportTraceServiceRequest()
    spans = traces.resource_spans.add().scope_spans.add().spans
    for event_id in event_ids:
        span = spans.add()
        span.name = 'collector.torture.trace'
        span.trace_id = uuid.uuid4().bytes
        span.span_id = uuid.uuid4().bytes[:8]
        span.start_time_unix_nano = 1
        span.end_time_unix_nano = 2
        span.attributes.append(_attribute(event_id))

    logs = ExportLogsServiceRequest()
    log_records = logs.resource_logs.add().scope_logs.add().log_records
    for event_id in event_ids:
        record = log_records.add()
        record.time_unix_nano = 1
        record.body.string_value = 'collector torture log'
        record.attributes.append(_attribute(event_id))

    metrics = ExportMetricsServiceRequest()
    metric = metrics.resource_metrics.add().scope_metrics.add().metrics.add()
    metric.name = 'collector.torture.gauge'
    for event_id in event_ids:
        point = metric.gauge.data_points.add()
        point.time_unix_nano = 1
        point.as_int = 1
        point.attributes.append(_attribute(event_id))

    return [
        OTLPRequest('traces', '/v1/traces', traces.SerializeToString(), event_ids),
        OTLPRequest('metrics', '/v1/metrics', metrics.SerializeToString(), event_ids),
        OTLPRequest('logs', '/v1/logs', logs.SerializeToString(), event_ids),
    ]


def _event_id(attributes: Iterable[KeyValue]) -> str | None:
    for attribute in attributes:
        if attribute.key == 'test.event_id' and attribute.value.WhichOneof('value') == 'string_value':
            return attribute.value.string_value
    return None


def _captured_event_ids(capture: CaptureStore) -> dict[Signal, list[str]]:
    traces = [
        event_id
        for request in capture.traces
        for resource_spans in request.resource_spans
        for scope_spans in resource_spans.scope_spans
        for span in scope_spans.spans
        if span.name == 'collector.torture.trace'
        if (event_id := _event_id(span.attributes)) is not None
    ]
    logs = [
        event_id
        for request in capture.logs
        for resource_logs in request.resource_logs
        for scope_logs in resource_logs.scope_logs
        for record in scope_logs.log_records
        if record.body.string_value == 'collector torture log'
        if (event_id := _event_id(record.attributes)) is not None
    ]
    metrics = [
        event_id
        for request in capture.metrics
        for resource_metrics in request.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name == 'collector.torture.gauge'
        for point in metric.gauge.data_points
        if (event_id := _event_id(point.attributes)) is not None
    ]
    return {'traces': traces, 'metrics': metrics, 'logs': logs}


def _post(
    session: OTLPExporterHttpSession, endpoint: str, request: OTLPRequest, *, timeout: float = 1
) -> requests.Response:
    return session.post(
        f'{endpoint}{request.path}',
        data=request.body,
        headers={'Content-Type': 'application/x-protobuf'},
        timeout=timeout,
    )


def _wait_for_requests(capture: CaptureStore, requests_: list[OTLPRequest], timeout: float = 20) -> None:
    expected: dict[Signal, frozenset[str]] = {request.signal: request.event_ids for request in requests_}

    def all_received(store: CaptureStore) -> bool:
        actual = _captured_event_ids(store)
        return all(event_ids <= set(actual[signal]) for signal, event_ids in expected.items())

    capture.wait_until(all_received, 'all uniquely identified OTLP records', timeout)


def test_collector_outage_retries_every_signal_without_loss(collector_harness: CollectorHarness) -> None:
    requests_ = _requests(uuid.uuid4().hex, count=25)

    with OTLPExporterHttpSession() as session:
        collector_harness.stop()
        try:
            for request in requests_:
                with pytest.raises((SuppressedConnectionError, requests.exceptions.ReadTimeout)):
                    _post(session, collector_harness.endpoint, request, timeout=0.2)
            retry_thread = session.retryer.thread
            assert retry_thread is not None
        finally:
            collector_harness.restart()

        retry_thread.join(timeout=30)
        assert not retry_thread.is_alive(), 'disk retry queue did not drain after the Collector recovered'
        _wait_for_requests(collector_harness.capture, requests_)

    captured = _captured_event_ids(collector_harness.capture)
    for request in requests_:
        counts = Counter(captured[request.signal])
        assert {event_id: counts[event_id] for event_id in request.event_ids} == dict.fromkeys(request.event_ids, 1)


def test_429_is_retried_inline_before_delivery(collector_harness: CollectorHarness) -> None:
    request = _requests(uuid.uuid4().hex, count=1)[0]
    proxy = HTTPFaultProxy(collector_harness.endpoint, [429])
    try:
        with OTLPExporterHttpSession() as session:
            response = _post(session, proxy.endpoint, request)

        assert response.status_code == 200
        proxy.wait_for_attempts(2)
        assert proxy.attempts == 2
        _wait_for_requests(collector_harness.capture, [request])
    finally:
        proxy.close()


def test_repeated_503_is_replayed_from_the_disk_queue(collector_harness: CollectorHarness) -> None:
    request = _requests(uuid.uuid4().hex, count=10)[0]
    proxy = HTTPFaultProxy(collector_harness.endpoint, [503, 503])
    try:
        with OTLPExporterHttpSession() as session:
            with pytest.raises(requests.exceptions.HTTPError):
                _post(session, proxy.endpoint, request)

            retry_thread = session.retryer.thread
            assert retry_thread is not None
            retry_thread.join(timeout=10)
            assert not retry_thread.is_alive(), 'disk retry queue did not drain after the 503 responses stopped'
            _wait_for_requests(collector_harness.capture, [request])

        assert proxy.attempts == 3
    finally:
        proxy.close()

    counts = Counter(_captured_event_ids(collector_harness.capture)['traces'])
    assert {event_id: counts[event_id] for event_id in request.event_ids} == dict.fromkeys(request.event_ids, 1)


def test_400_is_not_retried(collector_harness: CollectorHarness) -> None:
    request = _requests(uuid.uuid4().hex, count=1)[0]
    proxy = HTTPFaultProxy(collector_harness.endpoint, [400])
    try:
        with OTLPExporterHttpSession() as session:
            response = _post(session, proxy.endpoint, request)

        assert response.status_code == 400
        assert proxy.attempts == 1
        assert request.event_ids.isdisjoint(_captured_event_ids(collector_harness.capture)['traces'])
    finally:
        proxy.close()


def test_lost_success_response_retries_without_loss_but_may_duplicate(collector_harness: CollectorHarness) -> None:
    request = _requests(uuid.uuid4().hex, count=10)[0]
    proxy = HTTPFaultProxy(collector_harness.endpoint, ['drop_response'])
    try:
        with OTLPExporterHttpSession() as session:
            response = _post(session, proxy.endpoint, request)

        assert response.status_code == 200
        proxy.wait_for_attempts(2)
        _wait_for_requests(collector_harness.capture, [request])
    finally:
        proxy.close()

    counts = Counter(_captured_event_ids(collector_harness.capture)['traces'])
    assert {event_id: counts[event_id] for event_id in request.event_ids} == dict.fromkeys(request.event_ids, 2)
