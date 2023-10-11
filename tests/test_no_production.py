import os

import httpx
import pytest
from httpx import ConnectTimeout


@pytest.mark.skipif(os.environ.get('CI') != 'true', reason='Only run in CI')
def test_cant_hit_production():
    # In CI, we modify /etc/hosts to point api.logfire.dev and related hostnames to an unreachable IP.
    # This won't prevent us from hitting production while testing during local development, but it at least
    # ensures that CI will not pass if we accidentally introduce logic that causes us to hit production while
    # running the test suite.
    with pytest.raises(ConnectTimeout):
        # Checking just one endpoint should be sufficient to verify the change to /etc/hosts is working.
        httpx.get('http://api.logfire.dev', timeout=1)
