from __future__ import annotations

import inspect
import sys
import warnings
from typing import TYPE_CHECKING, Callable, Literal, Sequence

from ..constants import ONE_SECOND_IN_NANOSECONDS
from .import_hook import LogfireFinder
from .types import AutoTraceModule

if TYPE_CHECKING:
    from ..main import Logfire


def install_auto_tracing(
    logfire: Logfire,
    modules: Sequence[str] | Callable[[AutoTraceModule], bool] | None = None,
    *,
    check_imported_modules: Literal['error', 'warn', 'ignore'] = 'error',
    min_duration: float = 0,
) -> None:
    """Install automatic tracing.

    See `Logfire.install_auto_tracing` for more information.
    """
    if modules is None:
        frame = inspect.stack()[2]
        module = inspect.getmodule(frame[0])
        if module is None:  # pragma: no cover
            raise KeyError('module not found')
        modules = modules_func_from_sequence([module.__name__.split('.')[0]])
    elif isinstance(modules, Sequence):  # pragma: no branch
        modules = modules_func_from_sequence(modules)

    if not callable(modules):  # pragma: no cover
        raise TypeError('modules must be a list of strings or a callable')

    if check_imported_modules not in ('error', 'warn', 'ignore'):
        raise ValueError('check_imported_modules must be one of "error", "warn", or "ignore"')

    if check_imported_modules != 'ignore':
        for module in sys.modules.values():
            try:
                auto_trace_module = AutoTraceModule(module.__name__, module.__file__)
            except Exception:
                continue

            if modules(auto_trace_module):
                if check_imported_modules == 'error':
                    raise AutoTraceModuleAlreadyImportedException(
                        f'The module {module.__name__!r} matches modules to trace, but it has already been imported. '
                        f'Either call `install_auto_tracing` earlier, '
                        f"or set `check_imported_modules` to 'warn' or 'ignore'."
                    )
                else:
                    warnings.warn(
                        f'The module {module.__name__!r} matches modules to trace, but it has already been imported. '
                        f'Either call `install_auto_tracing` earlier, '
                        f"or set `check_imported_modules` to 'ignore'.",
                        AutoTraceModuleAlreadyImportedWarning,
                        stacklevel=2,
                    )

    min_duration = int(min_duration * ONE_SECOND_IN_NANOSECONDS)
    finder = LogfireFinder(logfire, modules, min_duration)
    sys.meta_path.insert(0, finder)


def modules_func_from_sequence(modules: Sequence[str]) -> Callable[[AutoTraceModule], bool]:
    return lambda module: module.parts_start_with(modules)


class AutoTraceModuleAlreadyImportedException(Exception):
    pass


class AutoTraceModuleAlreadyImportedWarning(Warning):
    pass
