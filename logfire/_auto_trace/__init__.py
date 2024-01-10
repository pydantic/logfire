from __future__ import annotations

import inspect
import sys
from typing import Callable, Sequence

from logfire._main import Logfire

from .import_hook import LogfireFinder
from .types import AutoTraceModule


def install_auto_tracing(
    modules: Sequence[str] | Callable[[AutoTraceModule], bool] | None = None, logfire: Logfire | None = None
) -> None:
    """Install automatic tracing.

    This will trace all function calls in the modules specified by the modules argument.
    It's equivalent to wrapping the body of every function in matching modules in `with logfire.span(...):`.

    NOTE: This function MUST be called before any of the modules are imported.

    This works by inserting a new meta path finder into `sys.meta_path`, so inserting another finder before it
    may prevent it from working.
    It relies on being able to retrieve the source code via at least one other existing finder in the meta path,
    so it may not work if standard finders are not present or if the source code is not available.
    A modified version of the source code is then compiled and executed in place of the original module.

    Args:
        modules: List of module names to trace, or a function which returns True for modules that should be traced.
                 If a list is provided, any submodules within a given module will also be traced.
                 Defaults to the root of the calling module, so e.g. calling this inside the module `foo.bar`
                 will trace all functions in `foo`, `foo.bar`, `foo.spam`, etc.
        logfire: The logfire instance to use. Defaults to the default logfire instance.
    """
    if modules is None:
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        if module is None:
            raise KeyError('module not found')
        modules = modules_func_from_sequence([module.__name__.split('.')[0]])
    elif isinstance(modules, Sequence):
        modules = modules_func_from_sequence(modules)

    if not callable(modules):
        raise TypeError('modules must be a list of strings or a callable')

    if logfire is None:
        from logfire import DEFAULT_LOGFIRE_INSTANCE

        logfire = DEFAULT_LOGFIRE_INSTANCE

    finder = LogfireFinder(logfire, modules)
    sys.meta_path.insert(0, finder)


def modules_func_from_sequence(modules: Sequence[str]) -> Callable[[AutoTraceModule], bool]:
    return lambda module: module.parts_start_with(modules)
