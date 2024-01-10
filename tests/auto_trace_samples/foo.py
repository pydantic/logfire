async def bar():
    lst = [x async for x in async_gen()]
    return lst[10]


def gen():
    yield from range(3)


async def async_gen():
    for x in gen():
        yield x
