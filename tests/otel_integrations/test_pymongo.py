from pymongo import monitoring

import logfire


# TODO real test
def test_instrument_pymongo():
    command_listeners = monitoring._LISTENERS.command_listeners  # type: ignore
    assert len(command_listeners) == 0  # type: ignore
    logfire.instrument_pymongo()
    assert len(command_listeners) == 1  # type: ignore
