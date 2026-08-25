from __future__ import annotations

import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import requests
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import KeyValue

from logfire._internal.exporters.otlp import DiskRetryer, OTLPExporterHttpSession
from logfire._internal.http_transport import (
    LogfireHTTPAdapter,
    install_connection_policy,
)
from tests.otel_collector.conftest import CaptureStore, CollectorHarness
from tests.otel_collector.faults import StaleConnectionProxy

pytestmark = pytest.mark.otel_collector


def _string_attribute(attributes: Iterable[KeyValue], key: str) -> str | None:
    for attribute in attributes:
        if attribute.key != key:
            continue
        value = attribute.value
        if value.WhichOneof('value') == 'string_value':
            return value.string_value
    return None


def _signals_captured_for_run(capture: CaptureStore, run_id: str) -> set[str]:
    signals: set[str] = set()
    if any(
        _string_attribute(span.attributes, 'test.run_id') == run_id
        for request in capture.traces
        for resource_spans in request.resource_spans
        for scope_spans in resource_spans.scope_spans
        for span in scope_spans.spans
    ):
        signals.add('traces')
    if any(
        _string_attribute(record.attributes, 'test.run_id') == run_id
        for request in capture.logs
        for resource_logs in request.resource_logs
        for scope_logs in resource_logs.scope_logs
        for record in scope_logs.log_records
    ):
        signals.add('logs')
    if any(
        _string_attribute(point.attributes, 'test.run_id') == run_id
        for request in capture.metrics
        for resource_metrics in request.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name == 'collector.conformance.counter'
        for point in metric.sum.data_points
    ):
        signals.add('metrics')
    return signals


def test_logfire_exports_all_signals_through_the_collector(collector_harness: CollectorHarness) -> None:
    run_id = uuid.uuid4().hex
    scenario = Path(__file__).with_name('scenario.py')
    result = subprocess.run(
        [sys.executable, str(scenario), '--endpoint', collector_harness.endpoint, '--run-id', run_id],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

    collector_harness.capture.wait_until(
        lambda capture: _signals_captured_for_run(capture, run_id) == {'traces', 'metrics', 'logs'},
        f'all signals for run {run_id}',
    )

    spans = [
        span
        for request in collector_harness.capture.traces
        for resource_spans in request.resource_spans
        for scope_spans in resource_spans.scope_spans
        for span in scope_spans.spans
        if _string_attribute(span.attributes, 'test.run_id') == run_id
    ]
    assert {span.name for span in spans} >= {'collector.conformance.parent', 'collector conformance log'}

    log_records = [
        record
        for request in collector_harness.capture.logs
        for resource_logs in request.resource_logs
        for scope_logs in resource_logs.scope_logs
        for record in scope_logs.log_records
        if _string_attribute(record.attributes, 'test.run_id') == run_id
    ]
    assert any(record.body.string_value == 'collector conformance otel log' for record in log_records)

    metrics = [
        metric
        for request in collector_harness.capture.metrics
        for resource_metrics in request.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name == 'collector.conformance.counter'
    ]
    assert metrics
    points = [point for metric in metrics for point in metric.sum.data_points]
    assert any(point.as_int == 7 and _string_attribute(point.attributes, 'test.run_id') == run_id for point in points)


@pytest.fixture
def stale_connection_proxy(collector_harness: CollectorHarness) -> Iterator[StaleConnectionProxy]:
    proxy = StaleConnectionProxy(collector_harness.host, collector_harness.http_port)
    try:
        yield proxy
    finally:
        proxy.close()


def _post_empty_trace(
    session: requests.Session,
    endpoint: str,
    timeout: float,
    *,
    proxies: dict[str, str] | None = None,
    verify: bool | str = True,
) -> requests.Response:
    return session.post(
        f'{endpoint}/v1/traces',
        data=ExportTraceServiceRequest().SerializeToString(),
        headers={'Content-Type': 'application/x-protobuf'},
        timeout=timeout,
        proxies=proxies,
        verify=verify,
    )


def _post_empty_trace_without_application_retry(
    session: OTLPExporterHttpSession,
    endpoint: str,
    timeout: float,
    *,
    proxies: dict[str, str] | None = None,
    verify: bool | str = True,
) -> requests.Response:
    return requests.Session.post(
        session,
        f'{endpoint}/v1/traces',
        data=ExportTraceServiceRequest().SerializeToString(),
        headers={'Content-Type': 'application/x-protobuf'},
        timeout=timeout,
        proxies=proxies,
        verify=verify,
    )


def test_https_pool_can_export_to_a_tls_collector(collector_harness: CollectorHarness) -> None:
    with OTLPExporterHttpSession() as session:
        response = session.post(
            f'{collector_harness.tls_endpoint}/v1/traces',
            data=ExportTraceServiceRequest().SerializeToString(),
            headers={'Content-Type': 'application/x-protobuf'},
            timeout=1,
            verify=collector_harness.certificate_path,
        )

    assert response.status_code == 200


def test_an_idle_stale_connection_is_recycled_before_reuse(stale_connection_proxy: StaleConnectionProxy) -> None:
    # Negative control: a normal requests session reuses the silently orphaned connection and
    # stalls until its read timeout. This proves the fixture distinguishes the regression.
    with requests.Session() as control:
        assert _post_empty_trace(control, stale_connection_proxy.endpoint, timeout=1).status_code == 200
        stale_connection_proxy.orphan_existing_connections()
        with pytest.raises(requests.exceptions.ReadTimeout):
            _post_empty_trace(control, stale_connection_proxy.endpoint, timeout=0.2)

    recycle_seconds = 0.1
    with OTLPExporterHttpSession() as session:
        install_connection_policy(session, idle_recycle_seconds=recycle_seconds)
        assert (
            _post_empty_trace_without_application_retry(session, stale_connection_proxy.endpoint, timeout=1).status_code
            == 200
        )
        stale_connection_proxy.orphan_existing_connections()
        time.sleep(recycle_seconds + 0.05)

        response = _post_empty_trace_without_application_retry(session, stale_connection_proxy.endpoint, timeout=1)

    assert response.status_code == 200


def test_disk_retryer_session_recycles_an_idle_stale_connection(
    stale_connection_proxy: StaleConnectionProxy,
) -> None:
    retryer = DiskRetryer({})
    try:
        adapter = retryer.session.get_adapter(stale_connection_proxy.endpoint)
        assert isinstance(adapter, LogfireHTTPAdapter)
        for pool_class in adapter.poolmanager.pool_classes_by_scheme.values():
            pool_class.idle_recycle_seconds = 0.1

        assert _post_empty_trace(retryer.session, stale_connection_proxy.endpoint, timeout=1).status_code == 200
        stale_connection_proxy.orphan_existing_connections()
        time.sleep(0.15)

        response = _post_empty_trace(retryer.session, stale_connection_proxy.endpoint, timeout=1)
    finally:
        retryer.close()

    assert response.status_code == 200


def test_idle_stale_connection_is_recycled_through_a_forward_proxy(
    collector_harness: CollectorHarness, stale_connection_proxy: StaleConnectionProxy
) -> None:
    target = f'http://{collector_harness.host}:{collector_harness.http_port}'
    proxies = {'http': stale_connection_proxy.endpoint}

    # Negative control: without Logfire's proxy-manager policy, requests reuses the silently
    # orphaned connection to the forward proxy and waits for the read timeout.
    with requests.Session() as control:
        assert _post_empty_trace(control, target, timeout=1, proxies=proxies).status_code == 200
        stale_connection_proxy.orphan_existing_connections()
        with pytest.raises(requests.exceptions.ReadTimeout):
            _post_empty_trace(control, target, timeout=0.2, proxies=proxies)

    recycle_seconds = 0.1
    with OTLPExporterHttpSession() as session:
        install_connection_policy(session, idle_recycle_seconds=recycle_seconds)
        assert (
            _post_empty_trace_without_application_retry(session, target, timeout=1, proxies=proxies).status_code == 200
        )
        stale_connection_proxy.orphan_existing_connections()
        time.sleep(recycle_seconds + 0.05)

        response = _post_empty_trace_without_application_retry(session, target, timeout=1, proxies=proxies)

    assert response.status_code == 200


def test_idle_stale_tls_tunnel_is_recycled_through_a_connect_proxy(
    collector_harness: CollectorHarness,
) -> None:
    proxy = StaleConnectionProxy(collector_harness.tls_host, collector_harness.tls_port, accept_connect=True)
    try:
        proxies = {'https': proxy.endpoint}
        verify = str(collector_harness.certificate_path)

        with requests.Session() as control:
            assert (
                _post_empty_trace(
                    control, collector_harness.tls_endpoint, timeout=1, proxies=proxies, verify=verify
                ).status_code
                == 200
            )
            proxy.orphan_existing_connections()
            with pytest.raises(requests.exceptions.ReadTimeout):
                _post_empty_trace(control, collector_harness.tls_endpoint, timeout=0.2, proxies=proxies, verify=verify)

        recycle_seconds = 0.1
        with OTLPExporterHttpSession() as session:
            install_connection_policy(session, idle_recycle_seconds=recycle_seconds)
            assert (
                _post_empty_trace_without_application_retry(
                    session, collector_harness.tls_endpoint, timeout=1, proxies=proxies, verify=verify
                ).status_code
                == 200
            )
            proxy.orphan_existing_connections()
            time.sleep(recycle_seconds + 0.05)

            response = _post_empty_trace_without_application_retry(
                session, collector_harness.tls_endpoint, timeout=1, proxies=proxies, verify=verify
            )
    finally:
        proxy.close()

    assert response.status_code == 200


def test_concurrent_idle_stale_connections_are_recycled(stale_connection_proxy: StaleConnectionProxy) -> None:
    concurrency = 8
    recycle_seconds = 0.1
    with OTLPExporterHttpSession() as session:
        install_connection_policy(session, idle_recycle_seconds=recycle_seconds)

        def request_wave() -> list[requests.Response]:
            barrier = threading.Barrier(concurrency)

            def send(_: int) -> requests.Response:
                barrier.wait(timeout=2)
                return _post_empty_trace_without_application_retry(session, stale_connection_proxy.endpoint, timeout=1)

            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                return list(executor.map(send, range(concurrency)))

        assert all(response.status_code == 200 for response in request_wave())
        assert stale_connection_proxy.connection_count > 1
        stale_connection_proxy.orphan_existing_connections()
        time.sleep(recycle_seconds + 0.05)

        assert all(response.status_code == 200 for response in request_wave())
