from ..main import Logfire as Logfire
from .rewrite_ast import exec_source as exec_source
from .types import AutoTraceModule as AutoTraceModule
from dataclasses import dataclass
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Callable, Sequence

@dataclass
class LogfireFinder(MetaPathFinder):
    """The import hook entry point, inserted into `sys.meta_path` to apply AST rewriting to matching modules."""
    logfire: Logfire
    modules_filter: Callable[[AutoTraceModule], bool]
    min_duration: int
    def find_spec(self, fullname: str, path: Sequence[str] | None, target: ModuleType | None = None) -> ModuleSpec | None:
        """This is the method that is called by the import system.

        It uses the other existing meta path finders to do most of the standard work,
        particularly finding the module's source code and filename.
        If it finds a module spec that matches the filter, it returns a new spec that uses the LogfireLoader.
        """
    def __init__(self, logfire, modules_filter, min_duration) -> None: ...

@dataclass
class LogfireLoader(Loader):
    """An import loader produced by LogfireFinder which executes a modified AST of the module's source code."""
    plain_spec: ModuleSpec
    source: str
    logfire: Logfire
    min_duration: int
    def exec_module(self, module: ModuleType):
        """Execute a modified AST of the module's source code in the module's namespace.

        This is called by the import system.
        """
    def create_module(self, spec: ModuleSpec): ...
    def __getattr__(self, item: str):
        """Forward some methods to the plain spec's loader (likely a `SourceFileLoader`) if they exist."""
    def __init__(self, plain_spec, source, logfire, min_duration) -> None: ...
