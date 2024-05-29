from typing import Any, Iterable, cast
from unittest.mock import Mock

import pytest
import requests.exceptions
from dirty_equals import IsFloat
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
    s.post('http://example.com', data='1234567890')
    with pytest.raises(BodyTooLargeError) as e:
        s.post('http://example.com', data='1234567890XXX')
    assert str(e.value) == 'Request body is too large (13 bytes), must be less than 10 bytes.'


def test_max_body_size_generator() -> None:
    s = OTLPExporterHttpSession(max_body_size=10)
    s.mount('http://', SinkHTTPAdapter())
    s.post('http://example.com', data=iter([b'abc'] * 3))
    with pytest.raises(BodyTooLargeError) as e:
        s.post('http://example.com', data=iter([b'abc'] * 100))
    assert str(e.value) == 'Request body is too large (12 bytes), must be less than 10 bytes.'


def test_connection_error_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_mock = Mock(return_value=0)
    monkeypatch.setattr('time.sleep', sleep_mock)

    class ConnectionErrorAdapter(HTTPAdapter):
        def send(self, request: PreparedRequest, *args: Any, **kwargs: Any) -> Response:
            raise requests.exceptions.ConnectionError()

    session = OTLPExporterHttpSession(max_body_size=10)
    session.mount('http://', ConnectionErrorAdapter())

    with pytest.raises(requests.exceptions.ConnectionError):
        session.post('http://example.com', data='123')

    assert [call.args for call in sleep_mock.call_args_list] == [
        (IsFloat(gt=1, lt=2),),
        (IsFloat(gt=2, lt=3),),
        (IsFloat(gt=4, lt=5),),
        (IsFloat(gt=8, lt=9),),
        (IsFloat(gt=16, lt=17),),
        (IsFloat(gt=32, lt=33),),
    ]
