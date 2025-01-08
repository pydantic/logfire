from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING
from uuid import UUID

from opentelemetry.sdk.trace.id_generator import RandomIdGenerator

_last_timestamp_v7 = None
_last_counter_v7 = 0

if TYPE_CHECKING:

    def uuid7() -> UUID: ...
else:
    # Try to use the built-in uuid7 function if it exists (Python 3.14+)
    # Or use the vendored implementation if it doesn't
    try:
        from uuid import uuid7  # type: ignore
    except ImportError:
        # vendored from https://github.com/python/cpython/pull/121119

        def uuid7() -> UUID:
            """Generate a UUID from a Unix timestamp in milliseconds and random bits.

            UUIDv7 objects feature monotonicity within a millisecond.
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
                rand = int.from_bytes(os.urandom(10))
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
                    tail = int.from_bytes(os.urandom(4))

            _last_timestamp_v7 = timestamp_ms
            _last_counter_v7 = counter

            int_uuid_7 = (timestamp_ms & 0xFFFF_FFFF_FFFF) << 80
            int_uuid_7 |= ((counter >> 30) & 0xFFF) << 64
            int_uuid_7 |= (counter & 0x3FFF_FFFF) << 32
            int_uuid_7 |= tail & 0xFFFF_FFFF
            return UUID(int=int_uuid_7, version=7)


class Uuidv7TraceIdGenerator(RandomIdGenerator):
    """The default ID generator for Logfire.

    Trace IDs are generated using UUIDv7, which have a timestamp and a counter prefix making
    them unique and sortable.
    Span IDs are generated using pure randomness.
    """

    def generate_trace_id(self) -> int:
        id = uuid7()
        return id.int
