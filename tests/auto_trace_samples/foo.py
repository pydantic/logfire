from typing import Iterator


async def bar():
    lst = [x async for x in async_gen()]
    return lst[10]


def gen() -> Iterator[int]:
    yield from range(3)


async def async_gen():
    def inner():
        return 1

    inner()

    for x in gen():  # pragma: no branch
        yield x
