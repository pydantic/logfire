import aiohttp
import pytest

import logfire


# TODO real test
@pytest.mark.anyio
async def test_instrument_aiohttp():
    cls = aiohttp.ClientSession
    original_init = cls.__init__
    assert cls.__init__ is original_init
    logfire.instrument_aiohttp_client()
    assert cls.__init__ is not original_init
