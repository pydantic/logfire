from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import cast

from opentelemetry.util import types as otel_types

from .constants import (
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_SAMPLE_RATE_KEY,
    ATTRIBUTES_TAGS_KEY,
)
from .stack_info import StackInfo, get_filepath_attribute
from .utils import uniquify_sequence


@dataclass(frozen=True)
class LogfireArgs:
    """Values passed to `logfire.instrument` and/or values stored in a logfire instance as basic configuration.

    These determine the arguments passed to the method calls added by the AST transformer.
    """

    tags: tuple[str, ...]
    sample_rate: float | None
    msg_template: str | None = None
    span_name: str | None = None


@dataclass
class BaseTransformer(ast.NodeTransformer):
    """Helper for rewriting ASTs to wrap function bodies in `with {logfire_method_name}(...):`."""

    logfire_args: LogfireArgs
    logfire_method_name: str
    filename: str
    module_name: str

    def __post_init__(self):
        # Names of functions and classes that we're currently inside,
        # so we can construct the qualified name of the current function.
        self.qualname_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        self.qualname_stack.append(node.name)
        # We need to call generic_visit here to modify any functions defined inside the class.
        node = cast(ast.ClassDef, self.generic_visit(node))
        self.qualname_stack.pop()
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        self.qualname_stack.append(node.name)
        qualname = '.'.join(self.qualname_stack)
        self.qualname_stack.append('<locals>')
        # We need to call generic_visit here to modify any classes/functions nested inside.
        self.generic_visit(node)
        self.qualname_stack.pop()  # <locals>
        self.qualname_stack.pop()  # node.name

        return self.rewrite_function(node, qualname)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        return self.visit_FunctionDef(node)

    def rewrite_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> ast.AST:
        # Replace the body of the function with:
        #     with <logfire_method_call_node>:
        #         <original body>
        body = node.body.copy()
        new_body: list[ast.stmt] = []
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            # If the first statement is just a string literal, it's a docstring.
            # Keep it as the first statement in the new body, not wrapped in a span,
            # so it's still recognized as a docstring.
            new_body.append(body.pop(0))

        # Ignore functions with a trivial/empty body:
        # - If `body` is empty, that means it originally was just a docstring that got popped above.
        # - If `body` is just a single `pass` statement
        # - If `body` is just a constant expression, particularly an ellipsis (`...`)
        if not body or (
            len(body) == 1
            and (
                isinstance(body[0], ast.Pass)
                or (isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant))
            )
        ):
            return node

        span = ast.With(
            items=[
                ast.withitem(
                    context_expr=self.logfire_method_call_node(node, qualname),
                )
            ],
            body=body,
            type_comment=node.type_comment,
        )
        new_body.append(span)

        return ast.fix_missing_locations(
            ast.copy_location(
                type(node)(  # type: ignore
                    name=node.name,
                    args=node.args,
                    body=new_body,
                    decorator_list=node.decorator_list,
                    returns=node.returns,
                    type_comment=node.type_comment,
                ),
                node,
            )
        )

    def logfire_method_call_node(self, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> ast.Call:
        raise NotImplementedError()

    def logfire_method_arg_values(self, qualname: str, lineno: int) -> tuple[str, dict[str, otel_types.AttributeValue]]:
        stack_info: StackInfo = {
            **get_filepath_attribute(self.filename),
            'code.lineno': lineno,
            'code.function': qualname,
        }
        attributes: dict[str, otel_types.AttributeValue] = {**stack_info}  # type: ignore

        logfire_args = self.logfire_args
        msg_template = logfire_args.msg_template or f'Calling {self.module_name}.{qualname}'
        attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] = msg_template

        span_name = logfire_args.span_name or msg_template

        if logfire_args.tags:
            attributes[ATTRIBUTES_TAGS_KEY] = uniquify_sequence(logfire_args.tags)

        sample_rate = logfire_args.sample_rate
        if sample_rate not in (None, 1):  # pragma: no cover
            attributes[ATTRIBUTES_SAMPLE_RATE_KEY] = sample_rate

        return span_name, attributes
