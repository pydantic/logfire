from redis import Redis

import logfire


# TODO real test
def test_instrument_redis():
    original = Redis.execute_command  # type: ignore
    assert Redis.execute_command is original  # type: ignore
    logfire.instrument_redis()
    assert Redis.execute_command is not original  # type: ignore
