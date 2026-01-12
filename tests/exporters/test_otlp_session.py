from typing import Any
from unittest.mock import Mock

import pytest
import requests
import requests.exceptions
from inline_snapshot import snapshot
from opentelemetry.sdk.trace.export import SpanExportResult
from requests.models import PreparedRequest, Response as Response
from requests.sessions import HTTPAdapter

from logfire._internal.exporters.otlp import (
    BodySizeCheckingOTLPSpanExporter,
    BodyTooLargeError,
    OTLPExporterHttpSession,
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


def test_connection_error_retries(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
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

    session = OTLPExporterHttpSession()
    headers = {'User-Agent': 'logfire', 'Authorization': 'Bearer 123'}
    session.headers.update(headers)

    # The main session always fails so that it defers to the retryer.
    session.mount('http://', ConnectionErrorAdapter(Mock(side_effect=requests.exceptions.ConnectionError())))

    # The retryer sessions fails at first to simulate logfire being down, then succeeds.
    failure = Response()
    failure.status_code = 500
    success = Response()
    success.status_code = 200
    num_exports = 10
    session.retryer.session.mount(
        'http://',
        ConnectionErrorAdapter(Mock(side_effect=[failure] * num_exports + [success] * num_exports)),
    )

    # Create a bunch of failed exports.
    for _ in range(num_exports):
        with pytest.raises(requests.exceptions.ConnectionError):
            session.post('http://example.com/', data=b'123')

    # Wait for the retryer to finish.
    # time.sleep has been mocked to return 0 so this shouldn't take long.
    assert session.retryer.thread
    session.retryer.thread.join()

    # Check that everything is cleaned up after succeeding.
    assert not session.retryer.tasks
    assert not session.retryer.thread
    assert not list(session.retryer.dir.iterdir())

    sleep_times = [call.args[0] for call in sleep_mock.call_args_list]
    # The initial sleep before the first retry is always 1 second.
    assert sleep_times.count(1) == num_exports
    # The initial sleeps are shuffled in randomly because of threads, so remove them before checking the rest.
    sleep_times = [t for t in sleep_times if t != 1]
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
