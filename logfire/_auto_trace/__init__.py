from __future__ import annotations

import inspect
import sys
from typing import TYPE_CHECKING, Callable, Sequence

from .import_hook import LogfireFinder
from .types import AutoTraceModule

if TYPE_CHECKING:
    from logfire._main import Logfire


def install_auto_tracing(
    logfire: Logfire, modules: Sequence[str] | Callable[[AutoTraceModule], bool] | None = None
) -> None:
    """Install automatic tracing.

    See `Logfire.install_auto_tracing` for more information.
    """
    if modules is None:
        frame = inspect.stack()[2]
        module = inspect.getmodule(frame[0])
        if module is None:
            raise KeyError('module not found')
        modules = modules_func_from_sequence([module.__name__.split('.')[0]])
    elif isinstance(modules, Sequence):
        modules = modules_func_from_sequence(modules)

    if not callable(modules):
        raise TypeError('modules must be a list of strings or a callable')

    finder = LogfireFinder(logfire, modules)
    sys.meta_path.insert(0, finder)


def modules_func_from_sequence(modules: Sequence[str]) -> Callable[[AutoTraceModule], bool]:
    return lambda module: module.parts_start_with(modules)
