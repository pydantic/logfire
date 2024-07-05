import ast
from .ast_utils import BaseTransformer as BaseTransformer, LogfireArgs as LogfireArgs
from .main import Logfire as Logfire
from dataclasses import dataclass
from types import CodeType
from typing import Callable

def instrument(logfire: Logfire, args: LogfireArgs) -> Callable[[Callable[_PARAMS, _RETURN]], Callable[_PARAMS, _RETURN]]: ...
def transform_code(func_code: CodeType, args: LogfireArgs): ...

@dataclass
class InstrumentTransformer(BaseTransformer):
    """Only modifies the function definition at the given line."""
    code_lineno: int
    def rewrite_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> ast.AST: ...
    def logfire_method_call_node(self, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> ast.Call: ...
    def logfire_method_arg_nodes(self, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> list[ast.expr]: ...
