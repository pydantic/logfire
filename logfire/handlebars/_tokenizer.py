"""Tokenizer for Handlebars templates.

Converts a template string into a stream of tokens that the parser can consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from logfire.handlebars._exceptions import HandlebarsParseError


class TokenType(Enum):
    """Types of tokens produced by the tokenizer."""

    # Content
    CONTENT = auto()

    # Comments
    COMMENT = auto()

    # Mustache delimiters
    OPEN = auto()  # {{
    CLOSE = auto()  # }}
    OPEN_UNESCAPED = auto()  # {{{
    CLOSE_UNESCAPED = auto()  # }}}
    OPEN_BLOCK = auto()  # {{#
    OPEN_ENDBLOCK = auto()  # {{/
    OPEN_INVERSE = auto()  # {{^
    OPEN_PARTIAL = auto()  # {{>

    # Raw block delimiters
    OPEN_RAW_BLOCK = auto()  # {{{{
    CLOSE_RAW_BLOCK = auto()  # }}}}
    END_RAW_BLOCK = auto()  # {{{{/
    RAW_CONTENT = auto()  # Content inside raw block

    # Expression components
    ID = auto()  # identifier
    DATA = auto()  # @data variable prefix
    SEP = auto()  # . or / separator
    PARENT = auto()  # ../
    OPEN_SEXPR = auto()  # (
    CLOSE_SEXPR = auto()  # )
    EQUALS = auto()  # = (in hash args)
    STRING = auto()  # "string" or 'string'
    NUMBER = auto()  # 42, 3.14, -1
    BOOLEAN = auto()  # true, false
    UNDEFINED = auto()  # undefined
    NULL = auto()  # null
    INVERSE = auto()  # else or ^

    # Block params
    OPEN_BLOCK_PARAMS = auto()  # as |
    CLOSE_BLOCK_PARAMS = auto()  # |

    # Whitespace control
    STRIP = auto()  # ~

    # End of input
    EOF = auto()


@dataclass(slots=True)
class Token:
    """A single token from the tokenizer.

    Attributes:
        type: The type of token.
        value: The string value of the token.
        line: Line number (1-based).
        column: Column number (1-based).
    """

    type: TokenType
    value: str
    line: int
    column: int


def tokenize(source: str) -> list[Token]:
    """Tokenize a Handlebars template string.

    Args:
        source: The template string to tokenize.

    Returns:
        A list of tokens.
    """
    return _TemplateTokenizer(source).tokenize()


class _TemplateTokenizer:
    """Tokenizes a Handlebars template string into a sequence of tokens."""

    def __init__(self, source: str) -> None:
        self._source = source
        self._pos = 0
        self._line = 1
        self._column = 1
        self._tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        """Tokenize the entire template."""
        while self._pos < len(self._source):
            self._read_next()
        self._tokens.append(Token(TokenType.EOF, '', self._line, self._column))
        return self._tokens

    def _peek(self, offset: int = 0) -> str:
        pos = self._pos + offset
        if pos < len(self._source):
            return self._source[pos]
        return ''

    def _starts_with(self, text: str) -> bool:
        return self._source[self._pos : self._pos + len(text)] == text

    def _advance(self, count: int = 1) -> str:
        text = self._source[self._pos : self._pos + count]
        for ch in text:
            if ch == '\n':
                self._line += 1
                self._column = 1
            else:
                self._column += 1
        self._pos += count
        return text

    def _emit(self, token_type: TokenType, value: str, line: int, column: int) -> None:
        self._tokens.append(Token(token_type, value, line, column))

    def _read_next(self) -> None:
        """Read the next token(s) from the source."""
        # Check for escaped mustache
        if self._starts_with('\\{{'):
            line, col = self._line, self._column
            self._advance(1)  # skip backslash
            content = self._advance(2)
            # Continue reading content
            more: list[str] = []
            while self._pos < len(self._source):
                if self._starts_with('\\{{'):
                    self._advance(1)
                    more.append(self._advance(2))
                    continue
                if self._starts_with('{{'):
                    break
                more.append(self._advance())
            self._emit(TokenType.CONTENT, content + ''.join(more), line, col)
            return

        # Check for raw block: {{{{
        if self._starts_with('{{{{') and not self._starts_with('{{{{/'):
            self._read_raw_block()
            return

        # Check for mustache open
        if self._starts_with('{{'):
            self._read_mustache()
            return

        # Read content
        self._read_content()

    def _read_content(self) -> None:
        """Read plain text content."""
        line, col = self._line, self._column
        content: list[str] = []

        while self._pos < len(self._source):
            if self._starts_with('\\{{'):
                self._advance(1)
                content.append(self._advance(2))
                continue
            if self._starts_with('{{'):
                break
            content.append(self._advance())

        if content:  # pragma: no branch
            self._emit(TokenType.CONTENT, ''.join(content), line, col)

    def _read_mustache(self) -> None:
        """Read a mustache tag ({{ ... }})."""
        line, col = self._line, self._column

        # Triple-stache (unescaped): {{{
        if self._starts_with('{{{') and not self._starts_with('{{{{'):
            self._advance(3)
            if self._peek() == '~':
                strip_l, strip_c = self._line, self._column
                self._advance()
                self._emit(TokenType.OPEN_UNESCAPED, '{{{', line, col)
                self._emit(TokenType.STRIP, '~', strip_l, strip_c)
            else:
                self._emit(TokenType.OPEN_UNESCAPED, '{{{', line, col)
            self._read_mustache_body(close_unescaped=True)
            return

        # Regular {{
        self._advance(2)
        self._read_regular_mustache(line, col)

    def _read_regular_mustache(self, line: int, col: int) -> None:
        """Read a regular mustache tag after consuming {{."""
        open_strip = False
        if self._peek() == '~':
            open_strip = True
            self._advance()

        next_ch = self._peek()

        if next_ch == '!':
            self._read_comment(line, col, open_strip)
            return

        # Map special characters to their token types
        special_map: dict[str, tuple[TokenType, str]] = {
            '#': (TokenType.OPEN_BLOCK, '{{#'),
            '/': (TokenType.OPEN_ENDBLOCK, '{{/'),
            '^': (TokenType.OPEN_INVERSE, '{{^'),
            '&': (TokenType.OPEN, '{{&'),
            '>': (TokenType.OPEN_PARTIAL, '{{>'),
        }

        if next_ch in special_map:
            self._advance()
            token_type, value = special_map[next_ch]
            self._emit(token_type, value, line, col)
            if open_strip:
                self._emit(TokenType.STRIP, '~', line, col + 2)
            self._read_mustache_body()
            return

        # Regular open
        self._emit(TokenType.OPEN, '{{', line, col)
        if open_strip:
            self._emit(TokenType.STRIP, '~', line, col + 2)
        self._read_mustache_body()

    def _read_comment(self, open_line: int, open_col: int, open_strip: bool) -> None:
        """Read a comment tag."""
        self._advance()  # consume !

        long_comment = self._starts_with('--')
        if long_comment:
            self._advance(2)

        comment_parts: list[str] = []

        if long_comment:
            while self._pos < len(self._source):
                if self._starts_with('--~}}'):
                    self._advance(5)
                    self._emit(TokenType.COMMENT, ''.join(comment_parts), open_line, open_col)
                    return
                if self._starts_with('--}}'):
                    self._advance(4)
                    self._emit(TokenType.COMMENT, ''.join(comment_parts), open_line, open_col)
                    return
                comment_parts.append(self._advance())
            raise HandlebarsParseError('Unclosed comment', line=open_line, column=open_col)
        else:
            while self._pos < len(self._source):
                if self._starts_with('~}}'):
                    self._advance(3)
                    self._emit(TokenType.COMMENT, ''.join(comment_parts), open_line, open_col)
                    return
                if self._starts_with('}}'):
                    self._advance(2)
                    self._emit(TokenType.COMMENT, ''.join(comment_parts), open_line, open_col)
                    return
                comment_parts.append(self._advance())
            raise HandlebarsParseError('Unclosed comment', line=open_line, column=open_col)

    def _read_mustache_body(self, close_unescaped: bool = False) -> None:
        """Read the body of a mustache tag."""
        while self._pos < len(self._source):
            self._skip_ws()

            if self._pos >= len(self._source):
                break

            # Check for strip before close: ~}}} or ~}}
            if self._peek() == '~':
                if close_unescaped and self._starts_with('~}}}'):
                    strip_l, strip_c = self._line, self._column
                    self._advance()  # ~
                    self._emit(TokenType.STRIP, '~', strip_l, strip_c)
                    close_l, close_c = self._line, self._column
                    self._advance(3)  # }}}
                    self._emit(TokenType.CLOSE_UNESCAPED, '}}}', close_l, close_c)
                    return
                if self._starts_with('~}}'):  # pragma: no branch
                    strip_l, strip_c = self._line, self._column
                    self._advance()  # ~
                    self._emit(TokenType.STRIP, '~', strip_l, strip_c)
                    close_l, close_c = self._line, self._column
                    self._advance(2)  # }}
                    self._emit(TokenType.CLOSE, '}}', close_l, close_c)
                    return

            # Close unescaped: }}}
            if close_unescaped and self._starts_with('}}}'):
                close_l, close_c = self._line, self._column
                self._advance(3)
                self._emit(TokenType.CLOSE_UNESCAPED, '}}}', close_l, close_c)
                return

            # Close: }}
            if self._starts_with('}}'):
                close_l, close_c = self._line, self._column
                self._advance(2)
                self._emit(TokenType.CLOSE, '}}', close_l, close_c)
                return

            # Read an expression token; track position to detect no-progress loops
            saved_pos = self._pos
            self._read_expression_token()
            if self._pos == saved_pos:
                # No progress — we're stuck on a character the tokenizer can't consume
                # (e.g., a lone '}' that doesn't form '}}' or '}}}')
                break

    def _skip_ws(self) -> None:
        """Skip whitespace inside a mustache expression."""
        while self._pos < len(self._source) and self._peek() in (' ', '\t', '\n', '\r'):
            self._advance()

    def _read_expression_token(self) -> None:
        """Read a single expression token."""
        if self._pos >= len(self._source):
            return  # pragma: no cover

        ch = self._peek()
        line, col = self._line, self._column

        if ch == '(':
            self._advance()
            self._emit(TokenType.OPEN_SEXPR, '(', line, col)
            return

        if ch == ')':
            self._advance()
            self._emit(TokenType.CLOSE_SEXPR, ')', line, col)
            return

        if ch == '=':
            self._advance()
            self._emit(TokenType.EQUALS, '=', line, col)
            return

        if ch == '|':
            self._advance()
            self._emit(TokenType.CLOSE_BLOCK_PARAMS, '|', line, col)
            return

        if ch in ('"', "'"):
            self._read_string()
            return

        if ch.isdigit() or (ch == '-' and self._peek(1).isdigit()):
            self._read_number()
            return

        if ch == '@':
            self._advance()
            self._emit(TokenType.DATA, '@', line, col)
            if self._pos < len(self._source) and (self._peek().isalnum() or self._peek() == '_'):
                self._read_id()
            return

        # Check for ../ before checking .
        if self._starts_with('../'):
            self._advance(3)
            self._emit(TokenType.PARENT, '../', line, col)
            return

        # Check for . as 'this' (standalone or followed by / or space or close)
        if ch == '.' and self._peek(1) in ('', ' ', '}', '~', ')', '/', '\t', '\n', '\r'):
            self._advance()
            self._emit(TokenType.ID, '.', line, col)
            if self._pos < len(self._source) and self._peek() == '/':
                sep_l, sep_c = self._line, self._column
                self._advance()
                self._emit(TokenType.SEP, '/', sep_l, sep_c)
            return

        # Path separators
        if ch in ('.', '/'):
            self._advance()
            self._emit(TokenType.SEP, ch, line, col)
            return

        # Identifier
        self._read_id()

    def _read_string(self) -> None:
        """Read a string literal."""
        line, col = self._line, self._column
        quote = self._advance()
        value: list[str] = []

        while self._pos < len(self._source):
            ch = self._peek()
            if ch == '\\':
                self._advance()
                if self._pos < len(self._source):  # pragma: no branch
                    escaped = self._advance()
                    if escaped == 'n':
                        value.append('\n')
                    elif escaped == 't':
                        value.append('\t')
                    elif escaped == 'r':
                        value.append('\r')
                    else:
                        value.append(escaped)
                continue
            if ch == quote:
                self._advance()
                self._emit(TokenType.STRING, ''.join(value), line, col)
                return
            value.append(self._advance())

        raise HandlebarsParseError('Unterminated string literal', line=line, column=col)

    def _read_number(self) -> None:
        """Read a number literal."""
        line, col = self._line, self._column
        num: list[str] = []

        if self._peek() == '-':
            num.append(self._advance())

        while self._pos < len(self._source) and self._peek().isdigit():
            num.append(self._advance())

        if self._pos < len(self._source) and self._peek() == '.':
            num.append(self._advance())
            while self._pos < len(self._source) and self._peek().isdigit():
                num.append(self._advance())

        self._emit(TokenType.NUMBER, ''.join(num), line, col)

    def _read_id(self) -> None:
        """Read an identifier."""
        line, col = self._line, self._column
        value: list[str] = []

        # Bracket notation
        if self._pos < len(self._source) and self._peek() == '[':
            self._advance()
            while self._pos < len(self._source) and self._peek() != ']':
                value.append(self._advance())
            if self._pos < len(self._source):
                self._advance()  # skip ]
            self._emit(TokenType.ID, ''.join(value), line, col)
            return

        while self._pos < len(self._source) and self._is_id_char(self._peek()):
            value.append(self._advance())

        if not value:
            ch = self._peek()
            if ch and ch not in ('}', '~', ' ', '\t', '\n', '\r', ')', '|', '='):
                self._advance()
                raise HandlebarsParseError(f'Unexpected character: {ch!r}', line=line, column=col)
            return  # pragma: no cover

        text = ''.join(value)

        if text in ('true', 'false'):
            self._emit(TokenType.BOOLEAN, text, line, col)
        elif text == 'null':
            self._emit(TokenType.NULL, text, line, col)
        elif text == 'undefined':
            self._emit(TokenType.UNDEFINED, text, line, col)
        elif text == 'else':
            self._emit(TokenType.INVERSE, text, line, col)
        elif text == 'as':
            # Check for 'as |'
            saved_pos = self._pos
            saved_line = self._line
            saved_col = self._column
            self._skip_ws()
            if self._pos < len(self._source) and self._peek() == '|':
                self._advance()
                self._emit(TokenType.OPEN_BLOCK_PARAMS, 'as |', line, col)
            else:
                self._pos = saved_pos
                self._line = saved_line
                self._column = saved_col
                self._emit(TokenType.ID, text, line, col)
        else:
            self._emit(TokenType.ID, text, line, col)

    def _read_raw_block(self) -> None:
        """Read a raw block: {{{{name}}}}...{{{{/name}}}}."""
        open_line = self._line
        open_col = self._column

        # Consume {{{{
        self._advance(4)
        self._emit(TokenType.OPEN_RAW_BLOCK, '{{{{', open_line, open_col)

        # Read the helper name
        self._skip_ws()
        name_line, name_col = self._line, self._column
        name_parts: list[str] = []
        while self._pos < len(self._source) and self._is_id_char(self._peek()):
            name_parts.append(self._advance())

        if not name_parts:
            raise HandlebarsParseError('Expected identifier in raw block', line=name_line, column=name_col)

        block_name = ''.join(name_parts)
        self._emit(TokenType.ID, block_name, name_line, name_col)

        self._skip_ws()

        # Expect }}}}
        if not self._starts_with('}}}}'):
            raise HandlebarsParseError(
                'Expected }}}} to close raw block open tag', line=self._line, column=self._column
            )

        close_l, close_c = self._line, self._column
        self._advance(4)
        self._emit(TokenType.CLOSE_RAW_BLOCK, '}}}}', close_l, close_c)

        # Read raw content until {{{{/name}}}}
        raw_l, raw_c = self._line, self._column
        raw_content: list[str] = []
        end_tag = '{{{{/' + block_name + '}}}}'

        while self._pos < len(self._source):
            if self._starts_with(end_tag):
                break
            raw_content.append(self._advance())

        if not self._starts_with(end_tag):
            raise HandlebarsParseError(f'Unclosed raw block: {block_name}', line=open_line, column=open_col)

        if raw_content:
            self._emit(TokenType.RAW_CONTENT, ''.join(raw_content), raw_l, raw_c)

        # Consume {{{{/name}}}}
        end_l, end_c = self._line, self._column
        self._advance(len(end_tag))
        self._emit(TokenType.END_RAW_BLOCK, block_name, end_l, end_c)

    @staticmethod
    def _is_id_char(ch: str) -> bool:
        """Check if a character is valid in an identifier."""
        return ch.isalnum() or ch in ('_', '$', '-')
