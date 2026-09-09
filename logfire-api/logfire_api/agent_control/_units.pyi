from _typeshed import Incomplete

MAX_TIMEOUT_MILLISECONDS: Incomplete
MAX_TIMEOUT_SECONDS: Incomplete

def is_representable_timeout(seconds: float) -> bool:
    """Whether a published `timeout` is a request budget an adapter can actually install.

    A timeout is representable when it is a finite, non-negative number of seconds no larger than
    [`MAX_TIMEOUT_SECONDS`][logfire.agent_control.MAX_TIMEOUT_SECONDS]. Everything else -- a negative
    budget, a `nan` that compares false against every deadline, an `inf` or an oversized value that
    wraps a 32-bit timer -- is refused rather than clamped, because each of them would make a request
    behave in a way nobody published: silently unlimited, or cancelled before it was sent.

    `0` is representable and means exactly what it says: a budget of no time at all.
    """
def to_milliseconds(seconds: float) -> int:
    '''A representable `timeout` in the integer milliseconds most SDKs and timers want.

    Rounded half up -- `floor(seconds * 1000 + 0.5)` -- which is the one rounding JavaScript\'s
    `Math.round` and Python agree on for non-negative values, so both cores return the same integer
    for the same published value. (Python\'s own `round` does not: it rounds halves to even, so
    `round(0.0025 * 1000)` is `2`, not `3`.)

    A *positive* budget never rounds down to `0`: anything under half a millisecond comes back as
    `1`. Zero milliseconds means "already expired" to a timer, so rounding a small positive budget
    into it would turn a very short timeout into a request that cannot be made at all. An exact `0`
    is passed through, since that is what it was published as.

    Raises:
        ValueError: when `seconds` is not representable; see `is_representable_timeout`, which is
            what an adapter should call first so the value is reported under its `OnUnmatched` policy
            rather than raised at conversion time.
    '''
