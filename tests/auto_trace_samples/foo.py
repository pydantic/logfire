from typing import Iterator

import logfire


async def bar():
    lst = [x async for x in async_gen()]
    return lst[10]


def gen() -> Iterator[int]:
    yield from range(3)


# @instrument oerrides auto-tracing
@logfire.instrument('Calling async_gen via @instrument')
async def async_gen():
    def inner():
        return 1

    inner()  # This is not traced

    for x in gen():  # pragma: no branch
        yield x
