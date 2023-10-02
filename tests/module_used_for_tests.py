from time import sleep
from typing import Callable, TypeVar

from typing_extensions import ParamSpec

P = ParamSpec('P')
T = TypeVar('T')


def wrap(f: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    sleep(0.05)
    return f(*args, **kwargs)
