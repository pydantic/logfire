import gc
import os
import subprocess
import sys
import textwrap
import weakref
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from inline_snapshot import snapshot
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.sdk.trace.export import SpanExportResult
from requests.models import PreparedRequest, Response as Response
from requests.sessions import HTTPAdapter

from logfire._internal.exporters.otlp import (
    BodySizeCheckingOTLPSpanExporter,
    BodyTooLargeError,
    DiskRetryer,
    ExportRetryInProgressError,
    OTLPExporterHttpSession,
    cleanup_disk_retryers,
)
from tests.exporters.test_retry_fewer_spans import TEST_SPANS


class SinkHTTPAdapter(HTTPAdapter):
    """An HTTPAdapter that consumes all data sent to it."""

    def send(self, request: PreparedRequest, *args: Any, **kwargs: Any) -> Response:
        resp = Response()
        resp.status_code = 200
        return resp


def test_max_body_size_bytes() -> None:
    session = OTLPExporterHttpSession()
    session.mount('http://', SinkHTTPAdapter())
    exporter = BodySizeCheckingOTLPSpanExporter(session=session)

    assert exporter.export(TEST_SPANS) == SpanExportResult.SUCCESS

    exporter.max_body_size = 10
    with pytest.raises(BodyTooLargeError) as e:
        exporter.export(TEST_SPANS)
    assert str(e.value) == snapshot('Request body is too large (897045 bytes), must be less than 10 bytes.')


def test_disk_retryer_retries(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    sleep_mock = Mock(return_value=0)
    monkeypatch.setattr('time.sleep', sleep_mock)
    monkeypatch.setattr('time.monotonic', Mock(side_effect=range(0, 1000, 30)))
    monkeypatch.setattr('random.random', Mock(return_value=0.5))

    class ConnectionErrorAdapter(HTTPAdapter):
        def __init__(self, mock: Mock):
            super().__init__()
            self.mock = mock

        def send(self, request: PreparedRequest, *args: Any, **kwargs: Any) -> Response:
            assert request.body == b'123'
            assert request.url == 'http://example.com/'
            assert request.headers['User-Agent'] == 'logfire'
            assert request.headers['Authorization'] == 'Bearer 123'
            return self.mock()

    headers = {'User-Agent': 'logfire', 'Authorization': 'Bearer 123'}
    retryer = DiskRetryer(headers)

    # The retryer sessions fails at first to simulate logfire being down, then succeeds.
    failure = Response()
    failure.status_code = 500
    success = Response()
    success.status_code = 200
    num_exports = 10
    retryer.session.mount(
        'http://',
        ConnectionErrorAdapter(Mock(side_effect=[failure] * num_exports + [success] * num_exports)),
    )

    # Create a bunch of failed exports.
    for _ in range(num_exports):
        retryer.add_task(b'123', {'url': 'http://example.com/'})

    # Wait for the retryer to finish.
    # time.sleep has been mocked to return 0 so this shouldn't take long.
    assert retryer.thread
    retryer.thread.join()

    # Check that everything is cleaned up after succeeding.
    assert not retryer.tasks
    assert not retryer.thread
    assert not list(retryer.dir.iterdir())

    sleep_times = [call.args[0] for call in sleep_mock.call_args_list]
    # random.random is mocked to return 0.5 so that the retry delay is always 1.5 * 2 ** n.
    # This means these numbers show the average time slept for each call,
    # e.g. 6.0 means the actual sleep would be between 4 and 8 seconds.
    sleep_times_exponential = [
        1.5,
        3.0,
        6.0,
        12.0,
        24.0,
        48.0,
        96.0,
        # This is where we reach the MAX_DELAY of 128 seconds.
        192.0,
        192.0,
        192.0,
        192.0,
        # The errors stop here and requests succeed, so the sleep time is reset.
        # There are 10 exports and the first one succeeded after the last 192s wait,
        # so that leaves 9 more short sleeps.
    ]
    assert sleep_times[: len(sleep_times_exponential)] == sleep_times_exponential
    sleep_times_after = sleep_times[len(sleep_times_exponential) :]
    assert len(sleep_times_after) == num_exports - 1
    # While there's still tasks to process, the base sleep time is reduced to 0.2 seconds.
    # When that loop ends, a new task may still be added and the loop restarts with a base time of 1 second.
    assert all(t in {0.2 * 1.5, 1.0 * 1.5} for t in sleep_times_after)

    # A message gets logged once per minute when an export fails.
    # time.monotonic is mocked to return a value increasing by 30 each time,
    # so for 10 failed exports we get 5 messages.
    assert len(caplog.messages) == 5
    # This will always be the first message in case of failures.
    # After that the number of failed exports is unpredictable because the main thread is adding to it
    # at the same time as the retryer thread removes from it.
    assert caplog.messages[0] == snapshot('Currently retrying 1 failed export(s) (3 bytes)')


def test_session_queues_without_network_when_retryer_active() -> None:
    class ActiveRetryer:
        add_task = Mock()

        @staticmethod
        def is_active() -> bool:
            return True

    session = OTLPExporterHttpSession()
    retryer = ActiveRetryer()
    session.__dict__['retryer'] = retryer
    session._post = Mock()  # type: ignore[method-assign]

    with pytest.raises(ExportRetryInProgressError):
        session.post('http://example.com/', data=b'123', timeout=5)

    session._post.assert_not_called()  # type: ignore[attr-defined]
    retryer.add_task.assert_called_once_with(b'123', {'url': 'http://example.com/', 'timeout': 5})


def test_open_circuit_does_not_trigger_otel_connection_error_retry() -> None:
    class ActiveRetryer:
        add_task = Mock()

        @staticmethod
        def is_active() -> bool:
            return True

    session = OTLPExporterHttpSession()
    retryer = ActiveRetryer()
    session.__dict__['retryer'] = retryer
    exporter = BodySizeCheckingOTLPSpanExporter(
        endpoint='http://example.com/v1/traces',
        session=session,
        compression=Compression.Gzip,
    )

    with pytest.raises(ExportRetryInProgressError):
        exporter.export(TEST_SPANS[:1])

    retryer.add_task.assert_called_once()


def test_disk_retryer_cleanup_after_logfire_shutdown(tmp_path: Path) -> None:
    retryer_dir = tmp_path / 'retryer-dir'
    marker_file = tmp_path / 'retryer-marker.txt'

    code = textwrap.dedent(
        """
        import os
        from pathlib import Path

        import requests
        import logfire
        from logfire._internal.exporters import otlp

        retryer_dir = Path(os.environ['LOGFIRE_RETRYER_DIR'])
        marker_file = Path(os.environ['LOGFIRE_RETRYER_MARKER'])

        original_mkdtemp = otlp.mkdtemp
        original_post = otlp.OTLPExporterHttpSession._post

        def fake_mkdtemp(prefix: str) -> str:
            marker_file.write_text(str(retryer_dir))
            retryer_dir.mkdir()
            return str(retryer_dir)

        def fail(self, url, data, **kwargs):
            raise requests.exceptions.RequestException('boom')

        otlp.mkdtemp = fake_mkdtemp
        otlp.OTLPExporterHttpSession._post = fail

        logfire.configure(send_to_logfire=True, token='pyt_foobar', inspect_arguments=False)
        logfire.info('hi')
        """
    )

    env = {
        **os.environ,
        'LOGFIRE_RETRYER_DIR': str(retryer_dir),
        'LOGFIRE_RETRYER_MARKER': str(marker_file),
    }
    result = subprocess.run([sys.executable, '-c', code], cwd=Path.cwd(), env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert marker_file.read_text() == str(retryer_dir)
    assert not retryer_dir.exists()


def test_cleanup_disk_retryers_skips_dead_weakrefs(monkeypatch: pytest.MonkeyPatch) -> None:
    live_retryer = DiskRetryer({})
    dead_retryer = DiskRetryer({})
    dead_ref = weakref.ref(dead_retryer)
    del dead_retryer
    gc.collect()

    monkeypatch.setattr(
        'logfire._internal.exporters.otlp._DISK_RETRYERS',
        [dead_ref, weakref.ref(live_retryer)],
    )

    cleanup_disk_retryers()

    assert dead_ref() is None
    assert not live_retryer.dir.exists()


def test_disk_retryer_close_during_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that _run exits when close() is called while the retry loop is active."""
    monkeypatch.setattr('random.random', Mock(return_value=0.5))

    retryer = DiskRetryer({})

    # Make the retryer session always fail so _run stays in the retry loop.
    failure = Response()
    failure.status_code = 500

    def failing_send(*args: Any, **kwargs: Any) -> Response:
        return failure

    monkeypatch.setattr(retryer.session, 'send', failing_send)

    # After a few sleeps, call close() so the retry loop checks self.closed and returns.
    sleep_count = 0

    def mock_sleep(seconds: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 3:
            retryer.close()

    monkeypatch.setattr('time.sleep', mock_sleep)

    retryer.add_task(b'123', {'url': 'http://example.com/'})

    # Capture thread reference before it can be set to None by close().
    thread = retryer.thread
    assert thread is not None
    thread.join(timeout=5)

    assert sleep_count >= 3
    assert retryer.closed


def test_disk_retryer_add_task_after_close_does_nothing() -> None:
    retryer = DiskRetryer({})
    retryer.close()

    retryer.add_task(b'123', {'url': 'http://example.com/'})

    assert retryer.total_size == 0
    assert not retryer.tasks
    assert retryer.thread is None
