from typing import Any, Iterable, cast
from unittest.mock import Mock

import pytest
import requests.exceptions
from requests.models import PreparedRequest, Response as Response
from requests.sessions import HTTPAdapter

from logfire._internal.exporters.otlp import BodyTooLargeError, OTLPExporterHttpSession


class SinkHTTPAdapter(HTTPAdapter):
    """An HTTPAdapter that consumes all data sent to it."""

    def send(self, request: PreparedRequest, *args: Any, **kwargs: Any) -> Response:
        total = 0
        if request.body is not None:  # pragma: no branch
            if isinstance(request.body, (str, bytes)):  # type: ignore
                total = len(request.body)
            else:
                # assume a generator
                body = request.body
                for chunk in cast(Iterable[bytes], body):
                    total += len(chunk)
        resp = Response()
        resp.status_code = 200
        resp._content = f'{total}'.encode()
        return resp


def test_max_body_size_bytes() -> None:
    s = OTLPExporterHttpSession(max_body_size=10)
    s.mount('http://', SinkHTTPAdapter())
    s.post('http://example.com', data=b'1234567890')
    with pytest.raises(BodyTooLargeError) as e:
        s.post('http://example.com', data=b'1234567890XXX')
    assert str(e.value) == 'Request body is too large (13 bytes), must be less than 10 bytes.'


def test_connection_error_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_mock = Mock(return_value=0)
    monkeypatch.setattr('time.sleep', sleep_mock)
    monkeypatch.setattr('random.random', Mock(return_value=0.5))

    success = Response()
    success.status_code = 200
    send_mock = Mock(side_effect=[requests.exceptions.ConnectionError()] * 4 + [success])

    class ConnectionErrorAdapter(HTTPAdapter):
        def send(self, request: PreparedRequest, *args: Any, **kwargs: Any) -> Response:
            assert request.body == b'123'
            assert request.url == 'http://example.com/'
            assert request.headers['User-Agent'] == 'logfire'
            assert request.headers['Authorization'] == 'Bearer 123'
            return send_mock()

    session = OTLPExporterHttpSession(max_body_size=10)
    headers = {'User-Agent': 'logfire', 'Authorization': 'Bearer 123'}
    session.headers.update(headers)
    session.mount('http://', ConnectionErrorAdapter())
    session.retryer.session.mount('http://', ConnectionErrorAdapter())

    with pytest.raises(requests.exceptions.ConnectionError):
        session.post('http://example.com/', data=b'123')

    assert session.retryer.thread
    session.retryer.thread.join()
    assert not session.retryer.tasks
    assert not session.retryer.thread
    assert not list(session.retryer.dir.iterdir())

    assert [call.args for call in sleep_mock.call_args_list] == [(1.5,), (3.0,), (6.0,), (12.0,)]
