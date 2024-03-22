from typing import Any, Iterable, cast

import pytest
from requests.models import PreparedRequest, Response as Response
from requests.sessions import HTTPAdapter

from logfire.exporters._otlp import BodyTooLargeError, OTLPExporterHttpSession


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
