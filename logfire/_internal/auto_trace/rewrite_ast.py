from __future__ import annotations

import ast
import inspect
import types
import uuid
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, Callable, ContextManager, TypeVar

import logfire

from ..ast_utils import BaseTransformer, LogfireArgs

if TYPE_CHECKING:
    from ..main import Logfire


def exec_source(
    source: str, filename: str, module_name: str, globs: dict[str, Any], logfire_instance: Logfire, min_duration: int
) -> None:
    """Execute a modified AST of the module's source code in the module's namespace.

    The modified AST wraps the body of every function definition in `with context_factories[index]():`.
    `context_factories` is added to the module's namespace as `logfire_<uuid>`.
    `index` is a different constant number for each function definition.
    `context_factories[index]` is one of these:
        - `partial(logfire_instance._fast_span, name, attributes)` where the name and attributes
            are constructed from `filename`, `module_name`, attributes of `logfire_instance`,
            and the qualified name and line number of the current function.
        - `MeasureTime`, a class that measures the time elapsed. If it exceeds `min_duration`,
            then `context_factories[index]` is replaced with the `partial` above.
    If `min_duration` is greater than 0, then `context_factories[index]` is initially `MeasureTime`.
    Otherwise, it's initially the `partial` above.
    """
    logfire_name = f'logfire_{uuid.uuid4().hex}'
    context_factories: list[Callable[[], ContextManager[Any]]] = []
    globs[logfire_name] = context_factories
    tree = rewrite_ast(source, filename, logfire_name, module_name, logfire_instance, context_factories, min_duration)
    assert isinstance(tree, ast.Module)  # for type checking
    # dont_inherit=True is necessary to prevent the module from inheriting the __future__ import from this module.
    code = compile(tree, filename, 'exec', dont_inherit=True)
    exec(code, globs, globs)


def rewrite_ast(
    source: str,
    filename: str,
    logfire_name: str,
    module_name: str,
    logfire_instance: Logfire,
    context_factories: list[Callable[[], ContextManager[Any]]],
    min_duration: int,
) -> ast.AST:
    tree = ast.parse(source)
    logfire_args = LogfireArgs(logfire_instance._tags + ('auto-trace',), logfire_instance._sample_rate)  # type: ignore
    transformer = AutoTraceTransformer(
        logfire_args, logfire_name, filename, module_name, logfire_instance, context_factories, min_duration
    )
    return transformer.visit(tree)


@dataclass
class AutoTraceTransformer(BaseTransformer):
    """Trace all encountered functions except those explicitly marked with `@no_auto_trace`."""

    logfire_instance: Logfire
    context_factories: list[Callable[[], ContextManager[Any]]]
    min_duration: int

    def check_no_auto_trace(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> bool:
        """Return true if the node has a `@no_auto_trace` or `@logfire.no_auto_trace` decorator."""
        return any(
            (
                isinstance(node, ast.Name)
                and node.id == no_auto_trace.__name__
                or (
                    isinstance(node, ast.Attribute)
                    and node.attr == no_auto_trace.__name__
                    and isinstance(node.value, ast.Name)
                    and node.value.id == logfire.__name__
                )
            )
            for node in node.decorator_list
        )

    def visit_ClassDef(self, node: ast.ClassDef):
        if self.check_no_auto_trace(node):
            return node

        return super().visit_ClassDef(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        if self.check_no_auto_trace(node):
            return node

        return super().visit_FunctionDef(node)

    def rewrite_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> ast.AST:
        if is_generator_function(node):
            return node

        return super().rewrite_function(node, qualname)

    def logfire_method_call_node(self, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> ast.Call:
        # See the exec_source docstring
        index = len(self.context_factories)
        span_factory = partial(
            self.logfire_instance._fast_span,  # type: ignore
            *self.logfire_method_arg_values(qualname, node.lineno),
        )
        if self.min_duration > 0:
            config = self.logfire_instance._config  # type: ignore

            # Local vars for fast access
            timer = config.ns_timestamp_generator
            min_duration = self.min_duration

            # This needs to be as fast as possible since it's the cost of auto-tracing a function
            # that never actually gets instrumented because its calls are all faster than `min_duration`.
            class MeasureTime:
                __slots__ = 'start'

                def __enter__(_self):
                    _self.start = timer()

                def __exit__(_self, *_):
                    if timer() - _self.start >= min_duration:
                        self.context_factories[index] = span_factory

            self.context_factories.append(MeasureTime)
        else:
            self.context_factories.append(span_factory)

        # This node means:
        #   context_factories[index]()
        # where `context_factories` is a global variable with the name `self.logfire_method_name`
        # pointing to the `self.context_factories` list.
        return ast.Call(
            func=ast.Subscript(
                value=ast.Name(id=self.logfire_method_name, ctx=ast.Load()),
                slice=ast.Index(value=ast.Constant(value=index)),  # type: ignore
                ctx=ast.Load(),
            ),
            args=[],
            keywords=[],
        )


T = TypeVar('T')


def no_auto_trace(x: T) -> T:
    """Decorator to prevent a function/class from being traced by `logfire.install_auto_tracing`.

    This is useful for small functions that are called very frequently and would generate too much noise.

    The decorator is detected at import time.
    Only `@no_auto_trace` or `@logfire.no_auto_trace` are supported.
    Renaming/aliasing either the function or module won't work.
    Neither will calling this indirectly via another function.

    Any decorated function, or any function defined anywhere inside a decorated function/class,
    will be completely ignored by `logfire.install_auto_tracing`.

    This decorator simply returns the argument unchanged, so there is zero runtime overhead.
    """
    return x  # pragma: no cover


GENERATOR_CODE_FLAGS = inspect.CO_GENERATOR | inspect.CO_ASYNC_GENERATOR


def is_generator_function(func_def: ast.FunctionDef | ast.AsyncFunctionDef):
    module_node = ast.parse('')
    module_node.body = [func_def]
    code = compile(module_node, '<string>', 'exec')
    return any(
        isinstance(const, types.CodeType) and (const.co_flags & GENERATOR_CODE_FLAGS) for const in code.co_consts
    )
