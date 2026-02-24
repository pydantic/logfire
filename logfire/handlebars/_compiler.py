"""Compiler/renderer for Handlebars templates.

Walks the AST and produces output given a context.
"""

from __future__ import annotations

from typing import Any, Protocol, cast

from logfire.handlebars._ast_nodes import (
    BlockStatement,
    BooleanLiteral,
    CommentStatement,
    ContentStatement,
    Expression,
    MustacheStatement,
    NullLiteral,
    NumberLiteral,
    PathExpression,
    Program,
    Statement,
    StringLiteral,
    SubExpression,
    UndefinedLiteral,
)
from logfire.handlebars._exceptions import HandlebarsRuntimeError
from logfire.handlebars._utils import SafeString, escape_expression, is_blocked_attribute, is_falsy, to_string

# Maximum nesting depth to prevent stack overflow
MAX_DEPTH = 100

# Maximum output size (10MB default)
MAX_OUTPUT_SIZE = 10 * 1024 * 1024


class HelperOptions:
    """Options passed to helper functions.

    Attributes:
        fn: Function to render the block content with a given context.
        inverse: Function to render the else/inverse content with a given context.
        hash: Hash arguments passed to the helper.
        data: Data variables (@root, @index, etc.).
        block_params: Block parameter values.
    """

    def __init__(
        self,
        *,
        fn: _BlockFn | None = None,
        inverse: _BlockFn | None = None,
        hash: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        block_params: list[str] | None = None,
    ) -> None:
        self.fn = fn or _noop_block
        self.inverse = inverse or _noop_block
        self.hash: dict[str, Any] = hash or {}
        self.data: dict[str, Any] = data or {}
        self.block_params: list[str] = block_params or []

    @property
    def name(self) -> str:
        """Get the helper name (for the log helper)."""
        return self.data.get('_name', '')


class _BlockFn(Protocol):
    def __call__(  # pragma: no cover
        self, context: Any = None, *, data: dict[str, Any] | None = None, block_params: list[Any] | None = None
    ) -> str: ...


def _noop_block(
    context: Any = None,
    *,
    data: dict[str, Any] | None = None,
    block_params: list[Any] | None = None,
) -> str:
    return ''


# Type for helper functions
HelperFunc = Any  # Can be various callable signatures


class Scope:
    """Represents a scope in the template execution.

    Manages the context chain, data variables, and block parameters.
    """

    def __init__(
        self,
        context: Any,
        parent: Scope | None = None,
        data: dict[str, Any] | None = None,
        block_params: dict[str, Any] | None = None,
    ) -> None:
        self.context = context
        self.parent = parent
        self.data: dict[str, Any] = dict(data) if data else {}
        self.block_params: dict[str, Any] = block_params or {}

        # Set @root
        if parent is None:
            self.data['root'] = context
        elif 'root' not in self.data:
            self.data['root'] = parent.data.get('root', context)

    def child(
        self,
        context: Any,
        data: dict[str, Any] | None = None,
        block_params: dict[str, Any] | None = None,
    ) -> Scope:
        """Create a child scope."""
        merged_data = dict(self.data)
        if data:
            merged_data.update(data)
        return Scope(context, parent=self, data=merged_data, block_params=block_params)

    def lookup_data(self, name: str) -> Any:
        """Look up a @data variable."""
        if name in self.data:
            return self.data[name]
        if self.parent is not None:
            return self.parent.lookup_data(name)
        return None

    def lookup_block_param(self, name: str) -> tuple[bool, Any]:
        """Look up a block parameter by name.

        Returns:
            Tuple of (found, value).
        """
        if name in self.block_params:
            return True, self.block_params[name]
        if self.parent is not None:
            return self.parent.lookup_block_param(name)
        return False, None

    def get_parent_context(self, depth: int) -> Any:
        """Walk up the scope chain to get a parent context."""
        scope: Scope = self
        for _ in range(depth):
            if scope.parent is None:
                return None
            scope = scope.parent
        return scope.context

    def get_parent_data(self, depth: int) -> dict[str, Any]:
        """Walk up the scope chain to get parent data."""
        scope: Scope = self
        for _ in range(depth):
            if scope.parent is None:
                return {}
            scope = scope.parent
        return scope.data


class Compiler:
    """Compiles/renders a Handlebars AST into a string."""

    def __init__(
        self,
        helpers: dict[str, HelperFunc] | None = None,
        *,
        max_depth: int = MAX_DEPTH,
        max_output_size: int = MAX_OUTPUT_SIZE,
    ) -> None:
        self._helpers: dict[str, HelperFunc] = helpers or {}
        self._max_depth = max_depth
        self._max_output_size = max_output_size
        self._depth = 0

    def render(self, program: Program, context: Any) -> str:
        """Render a program AST with the given context.

        Args:
            program: The AST to render.
            context: The data context.

        Returns:
            The rendered string.
        """
        scope = Scope(context)
        result = self._render_program(program, scope)

        if len(result) > self._max_output_size:
            raise HandlebarsRuntimeError(f'Output size exceeds maximum of {self._max_output_size} bytes')

        return result

    def _render_program(self, program: Program, scope: Scope) -> str:
        """Render a program (sequence of statements)."""
        self._depth += 1
        if self._depth > self._max_depth:
            raise HandlebarsRuntimeError(f'Maximum nesting depth of {self._max_depth} exceeded')

        try:
            parts: list[str] = []
            for stmt in program.body:
                rendered = self._render_statement(stmt, scope)
                parts.append(rendered)

            # Apply whitespace control
            return self._apply_whitespace_control(program.body, parts)
        finally:
            self._depth -= 1

    def _apply_whitespace_control(self, body: list[Statement], parts: list[str]) -> str:
        """Apply whitespace control (~ markers) to rendered parts."""
        adjusted = list(parts)

        for i, stmt in enumerate(body):
            strip = _get_strip_flags(stmt)
            if strip is None:
                continue

            open_strip, close_strip = strip

            # Strip whitespace from preceding content
            if open_strip and i > 0:
                adjusted[i - 1] = _rstrip_whitespace(adjusted[i - 1])

            # Strip whitespace from following content
            if close_strip and i < len(adjusted) - 1:
                adjusted[i + 1] = _lstrip_whitespace(adjusted[i + 1])

        return ''.join(adjusted)

    def _render_statement(self, stmt: Statement, scope: Scope) -> str:
        """Render a single statement."""
        if isinstance(stmt, ContentStatement):
            return stmt.value

        if isinstance(stmt, MustacheStatement):
            return self._render_mustache(stmt, scope)

        if isinstance(stmt, CommentStatement):
            return ''

        if isinstance(stmt, BlockStatement):
            return self._render_block(stmt, scope)

        # stmt is narrowed to RawBlock at this point
        return stmt.body

    def _render_mustache(self, stmt: MustacheStatement, scope: Scope) -> str:
        """Render a mustache expression."""
        # Check if this is a helper call (not a data variable, not a complex path)
        if (
            isinstance(stmt.path, PathExpression)
            and not stmt.path.data
            and stmt.path.depth == 0
            and not stmt.path.is_this
        ):
            helper_name = stmt.path.original
            if helper_name in self._helpers:
                # Helper always takes priority when there are params/hash
                # or when it's a single-part name registered as helper
                if stmt.params or stmt.hash_pairs or len(stmt.path.parts) == 1:
                    return self._call_helper_mustache(helper_name, stmt, scope)

        # Check for subexpression
        if isinstance(stmt.path, SubExpression):
            value = self._eval_subexpression(stmt.path, scope)
        else:
            value = self._eval_expression(stmt.path, scope)

        # If value is a helper and there are params, call it
        if callable(value) and stmt.params:
            args = [self._eval_expression(p, scope) for p in stmt.params]
            hash_args = {k: self._eval_expression(v, scope) for k, v in stmt.hash_pairs.items()}
            value = value(*args, **hash_args)

        result = to_string(value)

        if stmt.escaped and not isinstance(value, SafeString):
            result = escape_expression(result)

        return result

    def _call_helper_mustache(self, name: str, stmt: MustacheStatement, scope: Scope) -> str:
        """Call a helper from a mustache expression."""
        helper = self._helpers[name]
        args = [self._eval_expression(p, scope) for p in stmt.params]
        hash_args = {k: self._eval_expression(v, scope) for k, v in stmt.hash_pairs.items()}

        # Create options for potential block helper usage
        options = HelperOptions(
            hash=hash_args,
            data=scope.data,
        )

        # Try calling with different signatures
        try:
            if args:
                result = helper(*args, options=options)
            else:
                result = helper(scope.context, options=options)
        except TypeError:
            # Try simpler signature
            try:
                if args:
                    result = helper(*args, **hash_args)
                else:
                    result = helper(scope.context)
            except TypeError:
                result = helper()

        result_str = to_string(result)

        if stmt.escaped and not isinstance(result, SafeString):
            result_str = escape_expression(result_str)

        return result_str

    def _render_block(self, stmt: BlockStatement, scope: Scope) -> str:
        """Render a block statement."""
        if isinstance(stmt.path, PathExpression):
            helper_name = stmt.path.original

            # Check for registered block helpers
            if helper_name in self._helpers:
                return self._call_block_helper(helper_name, stmt, scope)

        # No helper - use context-based block behavior
        value = self._eval_expression(stmt.path, scope)

        if is_falsy(value):
            # Render inverse
            if stmt.inverse is not None:
                return self._render_program(stmt.inverse, scope)
            return ''

        if isinstance(value, list):
            # Iterate
            return self._render_each_inline(cast('list[Any]', value), stmt, scope)

        if isinstance(value, dict):
            # Change context
            child = scope.child(value)
            return self._render_program(stmt.body, child)

        if value is True:
            return self._render_program(stmt.body, scope)

        # Use value as context
        child = scope.child(value)
        return self._render_program(stmt.body, child)

    def _render_each_inline(self, items: list[Any], stmt: BlockStatement, scope: Scope) -> str:
        """Render a list using inline block iteration."""
        if not items:
            if stmt.inverse is not None:
                return self._render_program(stmt.inverse, scope)
            return ''

        parts: list[str] = []
        for i, item in enumerate(items):
            data = {
                'index': i,
                'first': i == 0,
                'last': i == len(items) - 1,
            }
            bp: dict[str, Any] = {}
            if stmt.block_params:
                bp[stmt.block_params[0]] = item
                if len(stmt.block_params) > 1:
                    bp[stmt.block_params[1]] = i
            child = scope.child(item, data=data, block_params=bp)
            parts.append(self._render_program(stmt.body, child))
        return ''.join(parts)

    def _call_block_helper(self, name: str, stmt: BlockStatement, scope: Scope) -> str:
        """Call a registered block helper."""
        helper = self._helpers[name]
        args = [self._eval_expression(p, scope) for p in stmt.params]
        hash_args = {k: self._eval_expression(v, scope) for k, v in stmt.hash_pairs.items()}

        compiler = self

        def fn(
            context: Any = None, *, data: dict[str, Any] | None = None, block_params: list[Any] | None = None
        ) -> str:
            ctx = context if context is not None else scope.context
            extra_data = data or {}
            bp: dict[str, Any] = {}
            if block_params and stmt.block_params:
                for j, bp_name in enumerate(stmt.block_params):
                    if j < len(block_params):
                        bp[bp_name] = block_params[j]
            child = scope.child(ctx, data=extra_data, block_params=bp)
            result = compiler._render_program(stmt.body, child)
            # Apply inner whitespace control from open/close tags
            if stmt.open_strip.close_standalone:
                result = _lstrip_whitespace(result)
            if stmt.close_strip.open_standalone:
                result = _rstrip_whitespace(result)
            return result

        def inverse(
            context: Any = None, *, data: dict[str, Any] | None = None, block_params: list[Any] | None = None
        ) -> str:
            if stmt.inverse is None:
                return ''
            ctx = context if context is not None else scope.context
            extra_data = data or {}
            bp: dict[str, Any] = {}
            if block_params and stmt.block_params:
                for j, bp_name in enumerate(stmt.block_params):
                    if j < len(block_params):
                        bp[bp_name] = block_params[j]

            # Handle chained blocks (else if)
            if stmt.inverse.body and isinstance(stmt.inverse.body[0], BlockStatement) and stmt.inverse.body[0].chained:
                return compiler._render_block(stmt.inverse.body[0], scope)

            child = scope.child(ctx, data=extra_data, block_params=bp)
            return compiler._render_program(stmt.inverse, child)

        options = HelperOptions(
            fn=fn,
            inverse=inverse,
            hash=hash_args,
            data=dict(scope.data, _name=name),
            block_params=stmt.block_params,
        )

        result = helper(scope.context, *args, options=options)
        return to_string(result)

    def _eval_expression(self, expr: Expression, scope: Scope) -> Any:
        """Evaluate an expression and return its value."""
        if isinstance(expr, StringLiteral):
            return expr.value

        if isinstance(expr, NumberLiteral):
            return expr.value

        if isinstance(expr, BooleanLiteral):
            return expr.value

        if isinstance(expr, (NullLiteral, UndefinedLiteral)):
            return None

        if isinstance(expr, SubExpression):
            return self._eval_subexpression(expr, scope)

        # After narrowing away all other Expression types, only PathExpression remains
        return self._resolve_path(expr, scope)

    def _eval_subexpression(self, expr: SubExpression, scope: Scope) -> Any:
        """Evaluate a subexpression (nested helper call)."""
        helper_name = expr.path.original

        if helper_name not in self._helpers:
            raise HandlebarsRuntimeError(f'Unknown helper: {helper_name}')

        helper = self._helpers[helper_name]
        args = [self._eval_expression(p, scope) for p in expr.params]
        hash_args = {k: self._eval_expression(v, scope) for k, v in expr.hash_pairs.items()}

        options = HelperOptions(hash=hash_args, data=scope.data)

        try:
            return helper(*args, options=options)
        except TypeError:
            try:
                return helper(*args, **hash_args)
            except TypeError:
                return helper(*args)

    def _resolve_path(self, path: PathExpression, scope: Scope) -> Any:
        """Resolve a path expression to its value."""
        # @data variables
        if path.data:
            return self._resolve_data_path(path, scope)

        # Block parameters take priority
        if path.parts and path.depth == 0 and not path.is_this:
            found, value = scope.lookup_block_param(path.parts[0])
            if found:
                for part in path.parts[1:]:
                    value = _get_property(value, part)
                return value

        # Get the starting context
        if path.depth > 0:
            context = scope.get_parent_context(path.depth)
        else:
            context = scope.context

        # 'this' with no parts returns the context itself
        if path.is_this and not path.parts:
            return context

        # Resolve parts
        value = context
        for part in path.parts:
            value = _get_property(value, part)
            if value is None:
                return None

        return value

    def _resolve_data_path(self, path: PathExpression, scope: Scope) -> Any:
        """Resolve a @data path, handling parent references."""
        # Handle parent data access: @../index
        if path.depth > 0:
            data = scope.get_parent_data(path.depth)
            if path.parts:
                value: Any = data.get(path.parts[0])
                for part in path.parts[1:]:
                    value = _get_property(value, part)
                return value
            return None

        if path.parts:
            value = scope.lookup_data(path.parts[0])
            for part in path.parts[1:]:
                value = _get_property(value, part)
            return value
        return None


def _get_property(obj: Any, name: str) -> Any:
    """Safely get a property from an object.

    Blocks access to dunder attributes and 'constructor'.
    """
    if is_blocked_attribute(name):
        return None

    if isinstance(obj, dict):
        return cast('dict[str, Any]', obj).get(name)

    if isinstance(obj, (list, tuple)):
        try:
            return cast('list[Any]', obj)[int(name)]
        except (ValueError, IndexError):
            return None

    # Try attribute access
    try:
        return getattr(obj, name)
    except AttributeError:
        return None


def _get_strip_flags(stmt: Statement) -> tuple[bool, bool] | None:
    """Get the strip flags (open, close) for a statement."""
    if isinstance(stmt, MustacheStatement):
        return stmt.strip.open_standalone, stmt.strip.close_standalone
    if isinstance(stmt, BlockStatement):
        return stmt.open_strip.open_standalone, stmt.close_strip.close_standalone
    if isinstance(stmt, CommentStatement):
        return stmt.strip.open_standalone, stmt.strip.close_standalone
    return None


def _rstrip_whitespace(s: str) -> str:
    """Strip trailing whitespace including the preceding newline."""
    return s.rstrip(' \t\r\n')


def _lstrip_whitespace(s: str) -> str:
    """Strip leading whitespace including the following newline."""
    return s.lstrip(' \t\r\n')
