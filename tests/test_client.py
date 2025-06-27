from __future__ import annotations

import pytest

from logfire._internal.auth import UserToken
from logfire._internal.client import LogfireClient


def test_client_expired_token() -> None:
    with pytest.raises(RuntimeError):
        LogfireClient(user_token=UserToken(token='abc', base_url='http://localhost', expiration='1970-01-01T00:00:00'))
