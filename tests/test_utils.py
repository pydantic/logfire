import pytest
import requests
import requests_mock

from logfire._internal.utils import UnexpectedResponse


def test_raise_for_status() -> None:
    with requests_mock.Mocker() as m:
        m.get('https://test.com', text='this is the body', status_code=503)
        r = requests.get('https://test.com')

    with pytest.raises(UnexpectedResponse) as exc_info:
        UnexpectedResponse.raise_for_status(r)
    s = str(exc_info.value)
    assert s.startswith('Unexpected response 503')
    assert 'body: this is the body' in s
