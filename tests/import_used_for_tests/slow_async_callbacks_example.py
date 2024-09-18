# The purpose of this file is to keep line numbers stable in tests, so make changes with care.

import asyncio

import logfire


async def main():
    asyncio.get_running_loop().call_soon(mock_block)
    await asyncio.create_task(foo(), name='foo 1')
    await asyncio.create_task(bar(), name='bar 1')


async def bar():
    await foo()
    mock_block()
    mock_block()
    await asyncio.create_task(foo(), name='foo 2')
    mock_block()
    mock_block()
    mock_block()
    raise RuntimeError('bar')


async def foo():
    await asyncio.sleep(0)
    mock_block()
    await asyncio.sleep(0)


def mock_block():
    # Simulate time advancing in a synchronous function.
    logfire.DEFAULT_LOGFIRE_INSTANCE.config.advanced.ns_timestamp_generator()
