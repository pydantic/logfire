from typing import Iterator

import logfire


async def bar():
    lst = [x for x in gen2()]
    return lst[10]


def gen() -> Iterator[int]:
    yield from range(3)


# @instrument overrides auto-tracing, but not functions within
@logfire.instrument('Calling gen2 via @instrument')
def gen2():
    def inner():
        return 1

    inner()

    for x in gen():  # pragma: no branch
        yield x * 2
