"""AST node definitions for the Handlebars parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


@dataclass(slots=True)
class PathExpression:
    """A path expression like `foo`, `foo.bar`, `../foo`, `this`, `@root`.

    Attributes:
        parts: The individual path segments (e.g., ['foo', 'bar'] for 'foo.bar').
        original: The original text of the path.
        depth: Number of parent scope references (../ count).
        is_this: Whether the path starts with 'this' or '.'.
        data: Whether this is a @data variable (e.g., @root, @index).
    """

    parts: list[str]
    original: str
    depth: int = 0
    is_this: bool = False
    data: bool = False


@dataclass(slots=True)
class StringLiteral:
    """A string literal like `"hello"` or `'hello'`."""

    value: str
    original: str


@dataclass(slots=True)
class NumberLiteral:
    """A numeric literal like `42` or `3.14` or `-1`."""

    value: int | float
    original: str


@dataclass(slots=True)
class BooleanLiteral:
    """A boolean literal: `true` or `false`."""

    value: bool
    original: str


@dataclass(slots=True)
class UndefinedLiteral:
    """The `undefined` literal."""

    original: str = 'undefined'


@dataclass(slots=True)
class NullLiteral:
    """The `null` literal."""

    original: str = 'null'


@dataclass(slots=True)
class SubExpression:
    """A subexpression like `(helper arg1 arg2 key=value)`.

    Attributes:
        path: The helper path.
        params: Positional arguments.
        hash_pairs: Keyword arguments.
    """

    path: PathExpression
    params: list[Expression]
    hash_pairs: dict[str, Expression]


# Union type for all expression nodes
Expression = Union[
    PathExpression, StringLiteral, NumberLiteral, BooleanLiteral, UndefinedLiteral, NullLiteral, SubExpression
]


@dataclass(slots=True)
class StripFlags:
    """Whitespace control flags.

    Attributes:
        open_standalone: Strip whitespace before open tag.
        close_standalone: Strip whitespace after close tag.
    """

    open_standalone: bool = False
    close_standalone: bool = False


@dataclass(slots=True)
class ContentStatement:
    """Raw text content between Handlebars expressions.

    Attributes:
        value: The text content.
        original: The original text (before whitespace stripping).
    """

    value: str
    original: str


@dataclass(slots=True)
class MustacheStatement:
    """A mustache expression like `{{foo}}`, `{{{foo}}}`, or `{{&foo}}`.

    Attributes:
        path: The expression path or helper name.
        params: Positional arguments to a helper.
        hash_pairs: Hash arguments (key=value pairs).
        escaped: Whether the output should be HTML-escaped.
        strip: Whitespace stripping configuration.
    """

    path: Expression
    params: list[Expression]
    hash_pairs: dict[str, Expression]
    escaped: bool = True
    strip: StripFlags = field(default_factory=StripFlags)


@dataclass(slots=True)
class CommentStatement:
    """A comment: `{{! ... }}` or `{{!-- ... --}}`.

    Attributes:
        value: The comment text.
        strip: Whitespace stripping configuration.
    """

    value: str
    strip: StripFlags = field(default_factory=StripFlags)


@dataclass(slots=True)
class BlockStatement:
    """A block expression like `{{#if condition}}...{{/if}}`.

    Attributes:
        path: The block helper path.
        params: Positional arguments.
        hash_pairs: Hash arguments.
        body: The main body program.
        inverse: The else/inverse body program (if any).
        open_strip: Whitespace stripping for the open tag.
        close_strip: Whitespace stripping for the close tag.
        inverse_strip: Whitespace stripping for the inverse tag.
        block_params: Block parameter names (e.g., |item index|).
        chained: Whether this block is part of a chained else-if.
    """

    path: Expression
    params: list[Expression]
    hash_pairs: dict[str, Expression]
    body: Program
    inverse: Program | None = None
    open_strip: StripFlags = field(default_factory=StripFlags)
    close_strip: StripFlags = field(default_factory=StripFlags)
    inverse_strip: StripFlags = field(default_factory=StripFlags)
    block_params: list[str] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    chained: bool = False


@dataclass(slots=True)
class RawBlock:
    """A raw block like `{{{{raw}}}}...{{{{/raw}}}}`.

    Content inside is not processed.

    Attributes:
        path: The block name path.
        body: The raw content string.
    """

    path: PathExpression
    body: str


# Union type for all statement nodes
Statement = Union[MustacheStatement, ContentStatement, CommentStatement, BlockStatement, RawBlock]


@dataclass(slots=True)
class Program:
    """The top-level AST node representing a complete template or block body.

    Attributes:
        body: List of statements in this program.
        block_params: Block parameter names if this is a block body.
    """

    body: list[Statement]
    block_params: list[str] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
