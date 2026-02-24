"""Parser for Handlebars templates.

Converts a token stream into an AST (Abstract Syntax Tree).
"""

from __future__ import annotations

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
    RawBlock,
    Statement,
    StringLiteral,
    StripFlags,
    SubExpression,
    UndefinedLiteral,
)
from logfire.handlebars._exceptions import HandlebarsParseError
from logfire.handlebars._tokenizer import Token, TokenType, tokenize


def parse(source: str) -> Program:
    """Parse a Handlebars template string into an AST.

    Args:
        source: The template string to parse.

    Returns:
        The parsed AST as a Program node.
    """
    tokens = tokenize(source)
    parser = _Parser(tokens, source)
    return parser.parse()


class _Parser:
    """Recursive descent parser for Handlebars templates."""

    def __init__(self, tokens: list[Token], source: str) -> None:
        self._tokens = tokens
        self._source = source
        self._pos = 0

    def parse(self) -> Program:
        """Parse the token stream into a Program AST node."""
        body = self._parse_body()
        return Program(body=body)

    def _current(self) -> Token:
        """Get the current token."""
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return Token(TokenType.EOF, '', 0, 0)  # pragma: no cover

    def _peek(self, offset: int = 0) -> Token:
        """Peek at a token ahead."""
        return self.token_at(offset)

    def token_at(self, offset: int = 0) -> Token:
        """Get a token at the given offset from the current position."""
        pos = self._pos + offset
        if pos < len(self._tokens):
            return self._tokens[pos]
        return Token(TokenType.EOF, '', 0, 0)  # pragma: no cover

    def _advance(self) -> Token:
        """Consume and return the current token."""
        token = self._current()
        self._pos += 1
        return token

    def _expect(self, token_type: TokenType) -> Token:
        """Consume the current token, expecting a specific type."""
        token = self._current()
        if token.type != token_type:
            raise HandlebarsParseError(
                f'Expected {token_type.name}, got {token.type.name} ({token.value!r})',
                line=token.line,
                column=token.column,
            )
        return self._advance()

    def _at_end(self) -> bool:
        """Check if we've reached the end of tokens."""
        return self._current().type == TokenType.EOF

    def _parse_body(self, end_condition: _EndCondition | None = None) -> list[Statement]:
        """Parse a sequence of statements until an end condition is met."""
        body: list[Statement] = []

        while not self._at_end():
            token = self._current()

            if end_condition is not None and end_condition.matches(token, self):
                break

            stmt = self._parse_statement()
            if stmt is not None:  # pragma: no branch
                body.append(stmt)

        # If we hit EOF while looking for a block close, that's an error
        if end_condition is not None and self._at_end() and not (end_condition.matches(self._current(), self)):
            raise HandlebarsParseError(
                'Unclosed block',
                line=self._current().line,
                column=self._current().column,
            )

        return body

    def _parse_statement(self) -> Statement | None:
        """Parse a single statement."""
        token = self._current()

        if token.type == TokenType.CONTENT:
            return self._parse_content()
        if token.type == TokenType.COMMENT:
            return self._parse_comment()
        if token.type == TokenType.OPEN:
            return self._parse_mustache()
        if token.type == TokenType.OPEN_UNESCAPED:
            return self._parse_mustache_unescaped()
        if token.type == TokenType.OPEN_BLOCK:
            return self._parse_block()
        if token.type == TokenType.OPEN_INVERSE:
            return self._parse_inverse_block()
        if token.type == TokenType.OPEN_RAW_BLOCK:
            return self._parse_raw_block()
        if token.type == TokenType.OPEN_ENDBLOCK:
            # This shouldn't happen at top level
            raise HandlebarsParseError(
                'Unexpected closing block',
                line=token.line,
                column=token.column,
            )
        if token.type == TokenType.OPEN_PARTIAL:
            raise HandlebarsParseError(
                'Partials are not supported',
                line=token.line,
                column=token.column,
            )

        # Skip unknown tokens
        self._advance()  # pragma: no cover
        return None  # pragma: no cover

    def _parse_content(self) -> ContentStatement:
        """Parse a content token."""
        token = self._advance()
        return ContentStatement(value=token.value, original=token.value)

    def _parse_comment(self) -> CommentStatement:
        """Parse a comment token."""
        token = self._advance()
        return CommentStatement(value=token.value)

    def _parse_mustache(self) -> MustacheStatement:
        """Parse a mustache expression: {{ ... }}."""
        open_token = self._advance()  # consume OPEN
        is_unescaped_amp = open_token.value == '{{&'

        open_strip = self._consume_strip()
        expr = self._parse_expression_with_params()
        close_strip = self._consume_strip()

        self._expect(TokenType.CLOSE)

        path, params, hash_pairs = expr
        escaped = not is_unescaped_amp

        strip = StripFlags(open_standalone=open_strip, close_standalone=close_strip)
        return MustacheStatement(
            path=path,
            params=params,
            hash_pairs=hash_pairs,
            escaped=escaped,
            strip=strip,
        )

    def _parse_mustache_unescaped(self) -> MustacheStatement:
        """Parse a triple-stache expression: {{{ ... }}}."""
        self._advance()  # consume OPEN_UNESCAPED

        open_strip = self._consume_strip()
        expr = self._parse_expression_with_params()
        close_strip = self._consume_strip()

        self._expect(TokenType.CLOSE_UNESCAPED)

        path, params, hash_pairs = expr
        strip = StripFlags(open_standalone=open_strip, close_standalone=close_strip)
        return MustacheStatement(
            path=path,
            params=params,
            hash_pairs=hash_pairs,
            escaped=False,
            strip=strip,
        )

    def _parse_block(self) -> BlockStatement:
        """Parse a block expression: {{#helper ...}}...{{/helper}}."""
        self._advance()  # consume OPEN_BLOCK

        open_strip_before = self._consume_strip()
        expr = self._parse_expression_with_params()
        block_params = self._parse_block_params()
        open_strip_after = self._consume_strip()

        self._expect(TokenType.CLOSE)

        path, params, hash_pairs = expr

        # Parse the body
        body_stmts = self._parse_body(_EndCondition.block_end(path))
        body = Program(body=body_stmts, block_params=block_params)

        inverse: Program | None = None
        inverse_strip = StripFlags()
        close_strip = StripFlags()

        # Check for inverse / else / chained else
        if self._current().type == TokenType.OPEN_INVERSE:
            inverse, inverse_strip, close_strip = self._parse_inverse_chain()
        elif self._current().type == TokenType.OPEN and self._is_else():
            inverse, inverse_strip, close_strip = self._parse_else_chain(path)

        # Consume the closing {{/helper}}
        if self._current().type == TokenType.OPEN_ENDBLOCK:  # pragma: no branch
            close_strip_before = self._consume_endblock_strip()
            close_strip = StripFlags(
                open_standalone=close_strip_before or close_strip.open_standalone,
                close_standalone=close_strip.close_standalone,
            )

            self._advance()  # OPEN_ENDBLOCK
            endblock_strip_open = self._consume_strip()
            self._parse_endblock_name(path)
            endblock_strip_close = self._consume_strip()
            self._expect(TokenType.CLOSE)

            close_strip = StripFlags(
                open_standalone=endblock_strip_open or close_strip.open_standalone,
                close_standalone=endblock_strip_close,
            )

        open_strip = StripFlags(
            open_standalone=open_strip_before,
            close_standalone=open_strip_after,
        )

        return BlockStatement(
            path=path,
            params=params,
            hash_pairs=hash_pairs,
            body=body,
            inverse=inverse,
            open_strip=open_strip,
            close_strip=close_strip,
            inverse_strip=inverse_strip,
            block_params=block_params,
        )

    def _parse_inverse_block(self) -> BlockStatement:
        """Parse an inverse block: {{^helper}}...{{/helper}} or standalone {{^}}."""
        open_token = self._advance()  # consume OPEN_INVERSE

        open_strip_before = self._consume_strip()

        # Check if this is a standalone {{^}} (shorthand for {{else}})
        # or {{^helper}}...{{/helper}}
        if self._current().type == TokenType.CLOSE:
            # Standalone {{^}} - this is handled in the block parsing as an inverse
            raise HandlebarsParseError(
                'Unexpected standalone inverse block',
                line=open_token.line,
                column=open_token.column,
            )

        expr = self._parse_expression_with_params()
        self._parse_block_params()
        open_strip_after = self._consume_strip()

        self._expect(TokenType.CLOSE)

        path, params, hash_pairs = expr

        # Parse body (this is the inverse body - will be empty)
        # Actually for {{^helper}}, the body is the "inverse" content
        body = Program(body=[])
        inverse_stmts = self._parse_body(_EndCondition.block_end(path))
        inverse = Program(body=inverse_stmts)

        # Consume the closing {{/helper}}
        close_strip = StripFlags()
        if self._current().type == TokenType.OPEN_ENDBLOCK:  # pragma: no branch
            self._advance()  # OPEN_ENDBLOCK
            endblock_strip_open = self._consume_strip()
            self._parse_endblock_name(path)
            endblock_strip_close = self._consume_strip()
            self._expect(TokenType.CLOSE)
            close_strip = StripFlags(
                open_standalone=endblock_strip_open,
                close_standalone=endblock_strip_close,
            )

        open_strip = StripFlags(
            open_standalone=open_strip_before,
            close_standalone=open_strip_after,
        )

        return BlockStatement(
            path=path,
            params=params,
            hash_pairs=hash_pairs,
            body=body,
            inverse=inverse,
            open_strip=open_strip,
            close_strip=close_strip,
        )

    def _parse_raw_block(self) -> RawBlock:
        """Parse a raw block: {{{{raw}}}}...{{{{/raw}}}}."""
        self._advance()  # OPEN_RAW_BLOCK

        # Parse the name
        name_token = self._expect(TokenType.ID)
        path = PathExpression(parts=[name_token.value], original=name_token.value)

        self._expect(TokenType.CLOSE_RAW_BLOCK)

        # Get raw content
        content = ''
        if self._current().type == TokenType.RAW_CONTENT:
            content = self._advance().value

        self._expect(TokenType.END_RAW_BLOCK)

        return RawBlock(path=path, body=content)

    def _is_else(self) -> bool:
        """Check if the current position has an {{else}} or {{^}} tag."""
        if self._current().type == TokenType.OPEN_INVERSE:
            return True  # pragma: no cover
        if self._current().type == TokenType.OPEN:
            # Look ahead for 'else'
            pos = self._pos + 1
            # Skip STRIP token
            if pos < len(self._tokens) and self._tokens[pos].type == TokenType.STRIP:
                pos += 1
            if pos < len(self._tokens) and self._tokens[pos].type == TokenType.INVERSE:  # pragma: no branch
                return True
        return False

    def _parse_inverse_chain(self) -> tuple[Program, StripFlags, StripFlags]:
        """Parse an inverse chain starting with {{^}}."""
        # Consume {{^
        self._advance()  # OPEN_INVERSE
        inv_strip_open = self._consume_strip()

        # Check if this is {{^}} or {{^ condition}} (chained else if)
        if self._current().type == TokenType.CLOSE:
            # Simple {{^}} (same as {{else}})
            inv_strip_close = self._consume_strip()
            self._expect(TokenType.CLOSE)

            inv_strip = StripFlags(open_standalone=inv_strip_open, close_standalone=inv_strip_close)

            # Parse inverse body until {{/
            inverse_stmts = self._parse_body(_EndCondition.endblock())
            return Program(body=inverse_stmts), inv_strip, StripFlags()

        # This has content - it's like a chained else if
        # Not standard Handlebars but we handle it
        inv_strip_close = self._consume_strip()
        self._expect(TokenType.CLOSE)

        inv_strip = StripFlags(open_standalone=inv_strip_open, close_standalone=inv_strip_close)
        inverse_stmts = self._parse_body(_EndCondition.endblock())
        return Program(body=inverse_stmts), inv_strip, StripFlags()

    def _parse_else_chain(self, block_path: Expression) -> tuple[Program, StripFlags, StripFlags]:
        """Parse an else chain: {{else}} or {{else if ...}}."""
        # Current token is OPEN
        self._advance()  # consume OPEN

        inv_strip_open = self._consume_strip()
        self._expect(TokenType.INVERSE)  # consume 'else'

        # Check for chained else: {{else if condition}}
        if self._current().type not in (TokenType.CLOSE, TokenType.STRIP):
            # This is {{else if ...}} - chained
            return self._parse_chained_else(block_path, inv_strip_open)

        inv_strip_close = self._consume_strip()
        self._expect(TokenType.CLOSE)

        inv_strip = StripFlags(open_standalone=inv_strip_open, close_standalone=inv_strip_close)

        # Parse the else body
        inverse_stmts = self._parse_body(_EndCondition.endblock_or_else())
        inverse = Program(body=inverse_stmts)

        close_strip = StripFlags()
        # Check for further chaining
        if self._is_else():  # pragma: no cover
            # Another else?? That shouldn't happen normally
            pass

        return inverse, inv_strip, close_strip

    def _parse_chained_else(
        self, block_path: Expression, inv_strip_open: bool
    ) -> tuple[Program, StripFlags, StripFlags]:
        """Parse a chained else-if: {{else if condition}}...."""
        # We just consumed 'else', now parse the helper expression
        expr = self._parse_expression_with_params()
        block_params = self._parse_block_params()
        inv_strip_close = self._consume_strip()

        self._expect(TokenType.CLOSE)

        path, params, hash_pairs = expr

        inv_strip = StripFlags(open_standalone=inv_strip_open, close_standalone=inv_strip_close)

        # Parse the body for this chained block
        body_stmts = self._parse_body(_EndCondition.endblock_or_else())
        body = Program(body=body_stmts, block_params=block_params)

        # Check for more chaining
        inner_inverse: Program | None = None
        inner_inv_strip = StripFlags()
        inner_close_strip = StripFlags()

        if self._current().type == TokenType.OPEN_INVERSE:
            inner_inverse, inner_inv_strip, inner_close_strip = self._parse_inverse_chain()
        elif self._is_else():
            inner_inverse, inner_inv_strip, inner_close_strip = self._parse_else_chain(block_path)

        # Create a block statement for this chained else-if
        chained_block = BlockStatement(
            path=path,
            params=params,
            hash_pairs=hash_pairs,
            body=body,
            inverse=inner_inverse,
            open_strip=StripFlags(),
            close_strip=inner_close_strip,
            inverse_strip=inner_inv_strip,
            block_params=block_params,
            chained=True,
        )

        # Wrap in a program
        inverse = Program(body=[chained_block])
        return inverse, inv_strip, StripFlags()

    def _parse_endblock_name(self, expected_path: Expression) -> None:
        """Parse and validate the name in a closing {{/name}} tag."""
        if not isinstance(expected_path, PathExpression):
            return  # pragma: no cover

        # Parse the path in the end block
        if self._current().type == TokenType.ID:  # pragma: no branch
            name = self._advance().value
            # Build full path
            while self._current().type == TokenType.SEP:
                self._advance()
                if self._current().type == TokenType.ID:  # pragma: no branch
                    name += '.' + self._advance().value
            if name != expected_path.original:
                raise HandlebarsParseError(
                    f"{expected_path.original} doesn't match {name}",
                    line=self._current().line,
                    column=self._current().column,
                )

    def _consume_strip(self) -> bool:
        """Consume a strip marker (~) if present, returning whether one was found."""
        if self._current().type == TokenType.STRIP:
            self._advance()
            return True
        return False

    def _consume_endblock_strip(self) -> bool:
        """Check if endblock has leading strip. Don't consume."""
        return False

    def _parse_block_params(self) -> list[str]:
        """Parse block parameters: as |param1 param2|."""
        if self._current().type != TokenType.OPEN_BLOCK_PARAMS:
            return []

        self._advance()  # consume 'as |'

        params: list[str] = []
        while self._current().type == TokenType.ID:
            params.append(self._advance().value)

        self._expect(TokenType.CLOSE_BLOCK_PARAMS)
        return params

    def _parse_expression_with_params(self) -> tuple[Expression, list[Expression], dict[str, Expression]]:
        """Parse an expression with optional params and hash arguments.

        Returns:
            Tuple of (expression, params, hash_pairs).
        """
        path = self._parse_expression()
        params: list[Expression] = []
        hash_pairs: dict[str, Expression] = {}

        while not self._at_end() and self._current().type not in (
            TokenType.CLOSE,
            TokenType.CLOSE_UNESCAPED,
            TokenType.CLOSE_RAW_BLOCK,
            TokenType.CLOSE_SEXPR,
            TokenType.STRIP,
            TokenType.OPEN_BLOCK_PARAMS,
            TokenType.EOF,
        ):
            # Check for hash argument: key=value
            if self._current().type == TokenType.ID and self._peek(1).type == TokenType.EQUALS:
                key = self._advance().value
                self._advance()  # consume =
                value = self._parse_expression()
                hash_pairs[key] = value
            else:
                params.append(self._parse_expression())

        return path, params, hash_pairs

    def _parse_expression(self) -> Expression:
        """Parse a single expression (path, literal, or subexpression)."""
        token = self._current()

        if token.type == TokenType.OPEN_SEXPR:
            return self._parse_subexpression()

        if token.type == TokenType.STRING:
            self._advance()
            return StringLiteral(value=token.value, original=token.value)

        if token.type == TokenType.NUMBER:
            self._advance()
            if '.' in token.value:
                return NumberLiteral(value=float(token.value), original=token.value)
            return NumberLiteral(value=int(token.value), original=token.value)

        if token.type == TokenType.BOOLEAN:
            self._advance()
            return BooleanLiteral(value=token.value == 'true', original=token.value)

        if token.type == TokenType.NULL:
            self._advance()
            return NullLiteral()

        if token.type == TokenType.UNDEFINED:
            self._advance()
            return UndefinedLiteral()

        return self._parse_path()

    def _parse_subexpression(self) -> SubExpression:
        """Parse a subexpression: (helper args...)."""
        self._expect(TokenType.OPEN_SEXPR)

        path = self._parse_path()
        params: list[Expression] = []
        hash_pairs: dict[str, Expression] = {}

        while self._current().type != TokenType.CLOSE_SEXPR:
            if self._at_end():
                raise HandlebarsParseError(
                    'Unclosed subexpression',
                    line=self._current().line,
                    column=self._current().column,
                )

            # Check for hash argument
            if self._current().type == TokenType.ID and self._peek(1).type == TokenType.EQUALS:
                key = self._advance().value
                self._advance()  # consume =
                value = self._parse_expression()
                hash_pairs[key] = value
            else:
                params.append(self._parse_expression())

        self._expect(TokenType.CLOSE_SEXPR)

        return SubExpression(path=path, params=params, hash_pairs=hash_pairs)

    def _parse_path(self) -> PathExpression:
        """Parse a path expression like foo, foo.bar, ../foo, @data, this.name."""
        parts: list[str] = []
        depth = 0
        is_data = False
        is_this = False
        original_parts: list[str] = []

        # Handle @data prefix
        if self._current().type == TokenType.DATA:
            is_data = True
            self._advance()
            original_parts.append('@')

        # Handle parent references
        while self._current().type == TokenType.PARENT:
            depth += 1
            original_parts.append('../')
            self._advance()

        # Handle 'this' or '.'
        if self._current().type == TokenType.ID and self._current().value in ('.', 'this'):
            is_this = True
            val = self._advance().value
            original_parts.append(val)
            # If followed by separator, consume it and read next segment
            if self._current().type == TokenType.SEP:
                original_parts.append(self._advance().value)
                # Read the segment after the separator
                if self._current().type == TokenType.ID:  # pragma: no branch
                    token = self._advance()
                    parts.append(token.value)
                    original_parts.append(token.value)
        elif self._current().type == TokenType.ID:
            token = self._advance()
            parts.append(token.value)
            original_parts.append(token.value)
        else:
            # This might be a boolean or other token used as a path
            raise HandlebarsParseError(
                f'Expected path expression, got {self._current().type.name}',
                line=self._current().line,
                column=self._current().column,
            )

        # Read subsequent path segments
        while self._current().type == TokenType.SEP:
            original_parts.append(self._advance().value)
            if self._current().type == TokenType.ID:
                token = self._advance()
                parts.append(token.value)
                original_parts.append(token.value)
            else:
                raise HandlebarsParseError(
                    'Expected identifier after path separator',
                    line=self._current().line,
                    column=self._current().column,
                )

        original = ''.join(original_parts)
        return PathExpression(
            parts=parts,
            original=original,
            depth=depth,
            is_this=is_this,
            data=is_data,
        )


class _EndCondition:
    """Defines when to stop parsing a body."""

    def __init__(
        self,
        *,
        end_block: bool = False,
        block_path: Expression | None = None,
        or_else: bool = False,
    ) -> None:
        self._end_block = end_block
        self._block_path = block_path
        self._or_else = or_else

    @classmethod
    def block_end(cls, path: Expression) -> _EndCondition:
        """Stop at {{/path}} or {{else}} or {{^}}."""
        return cls(end_block=True, block_path=path, or_else=True)

    @classmethod
    def endblock(cls) -> _EndCondition:
        """Stop at {{/...}}."""
        return cls(end_block=True)

    @classmethod
    def endblock_or_else(cls) -> _EndCondition:
        """Stop at {{/...}} or {{else}} or {{^}}."""
        return cls(end_block=True, or_else=True)

    def matches(self, token: Token, parser: _Parser) -> bool:
        """Check if the current token matches this end condition."""
        if self._end_block and token.type == TokenType.OPEN_ENDBLOCK:
            return True

        if self._or_else:
            # Check for {{^}}
            if token.type == TokenType.OPEN_INVERSE:
                return True

            # Check for {{else}} - OPEN followed by INVERSE
            if token.type == TokenType.OPEN:
                offset = 1
                # Skip STRIP
                if parser.token_at(offset).type == TokenType.STRIP:
                    offset += 1
                if parser.token_at(offset).type == TokenType.INVERSE:
                    return True

        return False
