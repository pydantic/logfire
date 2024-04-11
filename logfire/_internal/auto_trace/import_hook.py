from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from importlib.util import spec_from_loader
from types import ModuleType
from typing import TYPE_CHECKING, Callable, Iterator, Sequence

from .rewrite_ast import exec_source
from .types import AutoTraceModule

if TYPE_CHECKING:
    from ..main import Logfire


@dataclass
class LogfireFinder(MetaPathFinder):
    """The import hook entry point, inserted into `sys.meta_path` to apply AST rewriting to matching modules."""

    logfire: Logfire
    modules_filter: Callable[[AutoTraceModule], bool]
    min_duration: int

    def find_spec(
        self, fullname: str, path: Sequence[str] | None, target: ModuleType | None = None
    ) -> ModuleSpec | None:
        """This is the method that is called by the import system.

        It uses the other existing meta path finders to do most of the standard work,
        particularly finding the module's source code and filename.
        If it finds a module spec that matches the filter, it returns a new spec that uses the LogfireLoader.
        """
        for plain_spec in self._find_plain_specs(fullname, path, target):
            # Not all loaders have get_source, but it's an abstract method of the standard ABC InspectLoader.
            # In particular it's implemented by `importlib.machinery.SourceFileLoader`
            # which is provided by default.
            get_source = getattr(plain_spec.loader, 'get_source', None)
            if not callable(get_source):  # pragma: no cover
                continue

            try:
                source: str = get_source(fullname)
            except Exception:  # pragma: no cover
                continue

            if not source:
                continue

            if not self.modules_filter(AutoTraceModule(fullname, plain_spec.origin)):
                return None  # tell the import system to try the next meta path finder

            loader = LogfireLoader(plain_spec, source, self.logfire, self.min_duration)
            return spec_from_loader(fullname, loader)

    def _find_plain_specs(
        self, fullname: str, path: Sequence[str] | None, target: ModuleType | None
    ) -> Iterator[ModuleSpec]:
        """Yield module specs returned by other finders on `sys.meta_path`."""
        for finder in sys.meta_path:
            # Skip this finder or any like it to avoid infinite recursion.
            if isinstance(finder, LogfireFinder):
                continue

            try:
                plain_spec = finder.find_spec(fullname, path, target)
            except Exception:  # pragma: no cover
                continue

            if plain_spec:
                yield plain_spec


@dataclass
class LogfireLoader(Loader):
    """An import loader produced by LogfireFinder which executes a modified AST of the module's source code."""

    plain_spec: ModuleSpec
    """A spec for the module that was returned by another meta path finder (see `LogfireFinder._find_plain_specs`)."""

    source: str
    """The source code of the module, as returned by `plain_spec.loader.get_source(fullname)`."""

    logfire: Logfire
    min_duration: int

    def exec_module(self, module: ModuleType):
        """Execute a modified AST of the module's source code in the module's namespace.

        This is called by the import system.
        """
        # We fully expect self.plain_spec.origin, module.__file__, and self.get_filename(...)
        # to all be the same thing (a valid filename), but technically they're all optional,
        # so this is just an abundance of caution.
        filename = self.plain_spec.origin or module.__file__
        if not filename:  # pragma: no cover
            try:
                filename = self.get_filename(module.__name__)
            except Exception:
                pass
        filename = filename or f'<{module.__name__}>'

        exec_source(self.source, filename, module.__name__, module.__dict__, self.logfire, self.min_duration)

    # This is required when `exec_module` is defined.
    # It returns None to indicate that the usual module creation process should be used.
    def create_module(self, spec: ModuleSpec):
        return None

    def __getattr__(self, item: str):
        """Forward some methods to the plain spec's loader (likely a `SourceFileLoader`) if they exist."""
        if item in {'get_filename', 'is_package'}:
            return getattr(self.plain_spec.loader, item)
        raise AttributeError(item)
