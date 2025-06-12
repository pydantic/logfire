import importlib
from unittest import mock

import aiohttp
import aiohttp.web
import pytest
from inline_snapshot import snapshot

import logfire
import logfire._internal.integrations.aiohttp_server


# TODO real test
@pytest.mark.anyio
async def test_instrument_aiohttp_server():
    aiohttp_web = aiohttp.web
    original_application = getattr(aiohttp_web, 'Application', None)
    assert getattr(aiohttp_web, 'Application') is original_application
    logfire.instrument_aiohttp_server()
    assert getattr(aiohttp_web, 'Application') is not original_application


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict(
        'sys.modules', {'opentelemetry.instrumentation.aiohttp_server': None}
    ):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.aiohttp_server)
        assert str(exc_info.value) == snapshot(
            """\
`logfire.instrument_aiohttp_server()` requires the `opentelemetry-instrumentation-aiohttp-server` package.
You can install this with:
    pip install 'logfire[aiohttp-server]'\
"""
        )
