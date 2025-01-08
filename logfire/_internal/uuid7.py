from __future__ import annotations

import time
from random import Random

_last_timestamp_v7 = None
_last_counter_v7 = 0
_random = Random()


def uuid7(random: Random = _random) -> int:  # pragma: no cover
    """Generate a UUID from a Unix timestamp in milliseconds and random bits.

    UUIDv7 objects feature monotonicity within a millisecond.

    Vendored from https://github.com/python/cpython/pull/121119 w/ minor changes:

    1. Added a `random` argument to allow for seeding.
    2. Return an integer instead of a UUID object because:
     a. We need an integer anyway and would have just converted the UUID object to an integer
        (thus it's actually faster to do it this way than it will be in CPython!).
     b. The UUID object checks the version and variant, which currently rejects v7 UUIDs.
    """
    # --- 48 ---   -- 4 --   --- 12 ---   -- 2 --   --- 30 ---   - 32 -
    # unix_ts_ms | version | counter_hi | variant | counter_lo | random
    #
    # 'counter = counter_hi | counter_lo' is a 42-bit counter constructed
    # with Method 1 of RFC 9562, §6.2, and its MSB is set to 0.
    #
    # 'random' is a 32-bit random value regenerated for every new UUID.
    #
    # If multiple UUIDs are generated within the same millisecond, the LSB
    # of 'counter' is incremented by 1. When overflowing, the timestamp is
    # advanced and the counter is reset to a random 42-bit integer with MSB
    # set to 0.

    def get_counter_and_tail():
        rand = random.getrandbits(10)
        # 42-bit counter with MSB set to 0
        counter = (rand >> 32) & 0x1FF_FFFF_FFFF
        # 32-bit random data
        tail = rand & 0xFFFF_FFFF
        return counter, tail

    global _last_timestamp_v7
    global _last_counter_v7

    nanoseconds = time.time_ns()
    timestamp_ms, _ = divmod(nanoseconds, 1_000_000)

    if _last_timestamp_v7 is None or timestamp_ms > _last_timestamp_v7:
        counter, tail = get_counter_and_tail()
    else:
        if timestamp_ms < _last_timestamp_v7:
            timestamp_ms = _last_timestamp_v7 + 1
        # advance the 42-bit counter
        counter = _last_counter_v7 + 1
        if counter > 0x3FF_FFFF_FFFF:
            timestamp_ms += 1  # advance the 48-bit timestamp
            counter, tail = get_counter_and_tail()
        else:
            tail = int.from_bytes(random.getrandbits(4 * 8).to_bytes(4, 'little'))

    _last_timestamp_v7 = timestamp_ms
    _last_counter_v7 = counter

    int_uuid_7 = (timestamp_ms & 0xFFFF_FFFF_FFFF) << 80
    int_uuid_7 |= ((counter >> 30) & 0xFFF) << 64
    int_uuid_7 |= (counter & 0x3FFF_FFFF) << 32
    int_uuid_7 |= tail & 0xFFFF_FFFF

    return int_uuid_7
