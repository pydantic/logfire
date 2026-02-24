"""Tests for the Handlebars tokenizer."""

from __future__ import annotations

from logfire.handlebars._tokenizer import TokenType, tokenize


class TestTextTokenization:
    def test_plain_text(self) -> None:
        tokens = tokenize('Hello World')
        assert tokens[0].type == TokenType.CONTENT
        assert tokens[0].value == 'Hello World'
        assert tokens[1].type == TokenType.EOF

    def test_empty_string(self) -> None:
        tokens = tokenize('')
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF


class TestMustacheExpressions:
    def test_simple_expression(self) -> None:
        tokens = tokenize('{{name}}')
        types = [t.type for t in tokens]
        assert types == [TokenType.OPEN, TokenType.ID, TokenType.CLOSE, TokenType.EOF]
        assert tokens[1].value == 'name'

    def test_expression_with_text(self) -> None:
        tokens = tokenize('Hello {{name}}!')
        assert tokens[0].type == TokenType.CONTENT
        assert tokens[0].value == 'Hello '
        assert tokens[1].type == TokenType.OPEN
        assert tokens[2].type == TokenType.ID
        assert tokens[2].value == 'name'
        assert tokens[3].type == TokenType.CLOSE
        assert tokens[4].type == TokenType.CONTENT
        assert tokens[4].value == '!'

    def test_triple_stache(self) -> None:
        tokens = tokenize('{{{raw}}}')
        types = [t.type for t in tokens]
        assert types == [TokenType.OPEN_UNESCAPED, TokenType.ID, TokenType.CLOSE_UNESCAPED, TokenType.EOF]

    def test_path_expression(self) -> None:
        tokens = tokenize('{{person.name}}')
        types = [t.type for t in tokens]
        assert types == [
            TokenType.OPEN,
            TokenType.ID,
            TokenType.SEP,
            TokenType.ID,
            TokenType.CLOSE,
            TokenType.EOF,
        ]
        assert tokens[1].value == 'person'
        assert tokens[3].value == 'name'


class TestBlockTokens:
    def test_block_open(self) -> None:
        tokens = tokenize('{{#if}}')
        types = [t.type for t in tokens]
        assert types == [TokenType.OPEN_BLOCK, TokenType.ID, TokenType.CLOSE, TokenType.EOF]
        assert tokens[1].value == 'if'

    def test_block_close(self) -> None:
        tokens = tokenize('{{/if}}')
        types = [t.type for t in tokens]
        assert types == [TokenType.OPEN_ENDBLOCK, TokenType.ID, TokenType.CLOSE, TokenType.EOF]

    def test_inverse_block(self) -> None:
        tokens = tokenize('{{^}}')
        types = [t.type for t in tokens]
        assert types == [TokenType.OPEN_INVERSE, TokenType.CLOSE, TokenType.EOF]

    def test_partial(self) -> None:
        tokens = tokenize('{{>partial}}')
        types = [t.type for t in tokens]
        assert types == [TokenType.OPEN_PARTIAL, TokenType.ID, TokenType.CLOSE, TokenType.EOF]


class TestCommentTokens:
    def test_short_comment(self) -> None:
        tokens = tokenize('{{! this is a comment }}')
        types = [t.type for t in tokens]
        assert types == [TokenType.COMMENT, TokenType.EOF]
        assert 'this is a comment' in tokens[0].value

    def test_long_comment(self) -> None:
        tokens = tokenize('{{!-- long comment --}}')
        types = [t.type for t in tokens]
        assert types == [TokenType.COMMENT, TokenType.EOF]
        assert 'long comment' in tokens[0].value


class TestWhitespaceControlTokens:
    def test_strip_open(self) -> None:
        tokens = tokenize('{{~name}}')
        types = [t.type for t in tokens]
        assert TokenType.STRIP in types

    def test_strip_close(self) -> None:
        tokens = tokenize('{{name~}}')
        types = [t.type for t in tokens]
        assert TokenType.STRIP in types

    def test_strip_both(self) -> None:
        tokens = tokenize('{{~name~}}')
        strip_count = sum(1 for t in tokens if t.type == TokenType.STRIP)
        assert strip_count == 2


class TestLiteralTokens:
    def test_string_literal(self) -> None:
        tokens = tokenize('{{helper "hello"}}')
        types = [t.type for t in tokens]
        assert TokenType.STRING in types
        string_tok = next(t for t in tokens if t.type == TokenType.STRING)
        assert string_tok.value == 'hello'

    def test_number_literal(self) -> None:
        tokens = tokenize('{{helper 42}}')
        types = [t.type for t in tokens]
        assert TokenType.NUMBER in types
        num_tok = next(t for t in tokens if t.type == TokenType.NUMBER)
        assert num_tok.value == '42'

    def test_negative_number(self) -> None:
        tokens = tokenize('{{helper -1}}')
        num_tok = next(t for t in tokens if t.type == TokenType.NUMBER)
        assert num_tok.value == '-1'

    def test_float_number(self) -> None:
        tokens = tokenize('{{helper 3.14}}')
        num_tok = next(t for t in tokens if t.type == TokenType.NUMBER)
        assert num_tok.value == '3.14'

    def test_boolean_true(self) -> None:
        tokens = tokenize('{{helper true}}')
        bool_tok = next(t for t in tokens if t.type == TokenType.BOOLEAN)
        assert bool_tok.value == 'true'

    def test_boolean_false(self) -> None:
        tokens = tokenize('{{helper false}}')
        bool_tok = next(t for t in tokens if t.type == TokenType.BOOLEAN)
        assert bool_tok.value == 'false'

    def test_null(self) -> None:
        tokens = tokenize('{{helper null}}')
        null_tok = next(t for t in tokens if t.type == TokenType.NULL)
        assert null_tok.value == 'null'

    def test_undefined(self) -> None:
        tokens = tokenize('{{helper undefined}}')
        undef_tok = next(t for t in tokens if t.type == TokenType.UNDEFINED)
        assert undef_tok.value == 'undefined'


class TestDataVariables:
    def test_data_prefix(self) -> None:
        tokens = tokenize('{{@index}}')
        types = [t.type for t in tokens]
        assert TokenType.DATA in types

    def test_parent_ref(self) -> None:
        tokens = tokenize('{{../name}}')
        types = [t.type for t in tokens]
        assert TokenType.PARENT in types


class TestSubexpressionTokens:
    def test_subexpression(self) -> None:
        tokens = tokenize('{{helper (inner arg)}}')
        types = [t.type for t in tokens]
        assert TokenType.OPEN_SEXPR in types
        assert TokenType.CLOSE_SEXPR in types


class TestHashArgTokens:
    def test_equals_token(self) -> None:
        tokens = tokenize('{{helper key=value}}')
        types = [t.type for t in tokens]
        assert TokenType.EQUALS in types


class TestBlockParamsTokens:
    def test_block_params(self) -> None:
        tokens = tokenize('{{#each items as |item idx|}}')
        types = [t.type for t in tokens]
        assert TokenType.OPEN_BLOCK_PARAMS in types
        assert TokenType.CLOSE_BLOCK_PARAMS in types


class TestElseToken:
    def test_else_keyword(self) -> None:
        tokens = tokenize('{{else}}')
        types = [t.type for t in tokens]
        assert TokenType.INVERSE in types


class TestEscapedMustache:
    def test_escaped_open(self) -> None:
        tokens = tokenize('\\{{name}}')
        assert tokens[0].type == TokenType.CONTENT
        assert tokens[0].value == '{{name}}'


class TestRawBlock:
    def test_raw_block_tokens(self) -> None:
        tokens = tokenize('{{{{raw}}}}content{{{{/raw}}}}')
        types = [t.type for t in tokens]
        assert TokenType.OPEN_RAW_BLOCK in types
        assert TokenType.CLOSE_RAW_BLOCK in types
        assert TokenType.RAW_CONTENT in types
        assert TokenType.END_RAW_BLOCK in types


class TestLineColumnTracking:
    def test_first_token_position(self) -> None:
        tokens = tokenize('{{name}}')
        assert tokens[0].line == 1
        assert tokens[0].column == 1

    def test_multiline(self) -> None:
        tokens = tokenize('line1\n{{name}}')
        # The content token covers "line1\n"
        # The OPEN token starts on line 2
        open_tok = next(t for t in tokens if t.type == TokenType.OPEN)
        assert open_tok.line == 2
