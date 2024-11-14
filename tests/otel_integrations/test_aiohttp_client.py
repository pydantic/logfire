import importlib
from unittest import mock

import aiohttp
import pytest
from inline_snapshot import snapshot

import logfire
import logfire._internal.integrations.aiohttp_client


# TODO real test
@pytest.mark.anyio
async def test_instrument_aiohttp():
    cls = aiohttp.ClientSession
    original_init = cls.__init__
    assert cls.__init__ is original_init
    logfire.instrument_aiohttp_client()
    assert cls.__init__ is not original_init


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.aiohttp_client': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.aiohttp_client)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_aiohttp_client()` requires the `opentelemetry-instrumentation-aiohttp-client` package.
You can install this with:
    pip install 'logfire[aiohttp]'\
""")
