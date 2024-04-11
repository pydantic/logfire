from __future__ import annotations

import ast
import inspect
import uuid
from dataclasses import dataclass
from functools import lru_cache, update_wrapper
from types import CodeType, FunctionType
from typing import TYPE_CHECKING, Callable, Iterator, TypeVar

from typing_extensions import ParamSpec

from .ast_utils import BaseTransformer, LogfireArgs

if TYPE_CHECKING:
    from .main import Logfire


_PARAMS = ParamSpec('_PARAMS')
_RETURN = TypeVar('_RETURN')


def instrument(
    logfire: Logfire,
    args: LogfireArgs,
) -> Callable[[Callable[_PARAMS, _RETURN]], Callable[_PARAMS, _RETURN]]:
    def decorator(func: Callable[_PARAMS, _RETURN]) -> Callable[_PARAMS, _RETURN]:
        # This creates a new function object with code compiled from a modified AST
        # from the original function's source code.
        # Since this doesn't wrap/call the original function,
        # any decorators applied to the original function are 'lost', so the user shouldn't do that.

        if not isinstance(func, FunctionType):  # pragma: no cover
            raise ValueError(
                'You can only instrument pure Python functions. '
                'The decorator must be applied first, at the bottom of the list.'
            )

        if func.__dict__:  # pragma: no cover
            # This is just a rough check for other decorators.
            # In particular this will detect decorators that use functools.wraps.
            raise ValueError('The decorator must be applied first, at the bottom of the list.')

        func_code = func.__code__
        new_func_code, logfire_name = transform_code(func_code, args)
        new_func = FunctionType(new_func_code, func.__globals__, func.__name__, func.__defaults__, func.__closure__)
        update_wrapper(new_func, func)
        new_func.__kwdefaults__ = func.__kwdefaults__
        if args.extract_args:
            span_func = logfire._instrument_span_with_args  # type: ignore
        else:
            span_func = logfire._fast_span  # type: ignore
        new_func.__globals__[logfire_name] = span_func
        return new_func  # type: ignore

    return decorator


# The expensive work of retrieving source code, parsing, transforming, and compiling is cached here.
# The cache size is limited in case the decorator is called with highly variable arguments.
@lru_cache(maxsize=4096)
def transform_code(func_code: CodeType, args: LogfireArgs):
    logfire_name = f'logfire_{uuid.uuid4().hex}'

    if func_code.co_name == (lambda: 0).__code__.co_name:  # pragma: no cover
        raise ValueError('lambda functions cannot be instrumented')

    module = inspect.getmodule(func_code)
    assert module is not None
    filename = inspect.getsourcefile(func_code)

    # We have to process the entire source file, not just the function definition,
    # so that the compiled code has the correct context for things like closures.
    file_source_lines, _ = inspect.findsource(func_code)
    assert filename is not None
    file_source = ''.join(file_source_lines)
    tree = ast.parse(file_source)
    transformer = InstrumentTransformer(args, logfire_name, filename, module.__name__, func_code.co_firstlineno)
    tree = transformer.visit(tree)
    new_file_code = compile(tree, filename, 'exec', dont_inherit=True)

    # Recursively walk through the compiled code (starting from the module)
    # to find the compiled code for the function we're instrumenting.

    def find_code(root_code: CodeType) -> Iterator[CodeType]:
        for const in root_code.co_consts:
            if not isinstance(const, CodeType):
                continue
            matches = const.co_firstlineno == func_code.co_firstlineno and const.co_name == func_code.co_name
            if matches:
                yield const
            yield from find_code(const)

    [new_func_code] = find_code(new_file_code)
    return new_func_code, logfire_name


@dataclass
class InstrumentTransformer(BaseTransformer):
    """Only modifies the function definition at the given line."""

    code_lineno: int

    def rewrite_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> ast.AST:
        # For some reason, code.co_firstlineno starts at the first decorator.
        if node.decorator_list:
            lineno = node.decorator_list[0].lineno
        else:
            lineno = node.lineno

        if lineno != self.code_lineno:
            return node

        return super().rewrite_function(node, qualname)

    def logfire_method_call_node(self, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> ast.Call:
        return ast.Call(
            func=ast.Name(id=self.logfire_method_name, ctx=ast.Load()),
            args=self.logfire_method_arg_nodes(node, qualname),
            keywords=[],
        )

    def logfire_method_arg_nodes(self, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> list[ast.expr]:
        msg, attributes = self.logfire_method_arg_values(qualname, node.lineno)
        attributes_stmt = ast.parse(repr(attributes)).body[0]
        assert isinstance(attributes_stmt, ast.Expr)
        attributes_node = attributes_stmt.value
        result = [ast.Constant(value=msg), attributes_node]
        if self.logfire_args.extract_args:
            args = node.args
            arg_names = [
                arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg) if arg
            ]
            result.append(
                ast.Dict(
                    keys=[ast.Constant(value=name) for name in arg_names],
                    values=[ast.Name(id=name, ctx=ast.Load()) for name in arg_names],
                )
            )
        return result
