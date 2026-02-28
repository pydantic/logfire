"""Tests for basic Handlebars rendering via the public API."""

from __future__ import annotations

from logfire.handlebars import SafeString, compile, render


class TestSimpleVariableSubstitution:
    def test_simple_variable(self) -> None:
        assert render('Hello {{name}}!', {'name': 'World'}) == 'Hello World!'

    def test_multiple_variables(self) -> None:
        result = render('{{first}} {{last}}', {'first': 'John', 'last': 'Doe'})
        assert result == 'John Doe'

    def test_variable_with_surrounding_text(self) -> None:
        assert render('a{{x}}b', {'x': '!'}) == 'a!b'


class TestNestedPathAccess:
    def test_dot_notation(self) -> None:
        assert render('{{person.name}}', {'person': {'name': 'Alice'}}) == 'Alice'

    def test_deeply_nested(self) -> None:
        ctx = {'a': {'b': {'c': 'deep'}}}
        assert render('{{a.b.c}}', ctx) == 'deep'


class TestMissingVariable:
    def test_missing_returns_empty(self) -> None:
        assert render('Hello {{name}}!', {}) == 'Hello !'

    def test_missing_nested_returns_empty(self) -> None:
        assert render('{{a.b.c}}', {}) == ''

    def test_missing_intermediate_returns_empty(self) -> None:
        assert render('{{a.b}}', {'a': {}}) == ''


class TestLiterals:
    def test_string_literal_in_helper(self) -> None:
        result = render('{{uppercase "hello"}}', {})
        assert result == 'HELLO'

    def test_number_literal_in_helper(self) -> None:
        result = render('{{eq 1 1}}', {})
        assert result == 'true'

    def test_boolean_true_literal(self) -> None:
        result = render('{{#if true}}yes{{/if}}', {})
        assert result == 'yes'

    def test_boolean_false_literal(self) -> None:
        result = render('{{#if false}}yes{{else}}no{{/if}}', {})
        assert result == 'no'


class TestHTMLEscaping:
    def test_escapes_angle_brackets(self) -> None:
        assert render('{{val}}', {'val': '<b>bold</b>'}) == '&lt;b&gt;bold&lt;/b&gt;'

    def test_escapes_ampersand(self) -> None:
        assert render('{{val}}', {'val': 'a & b'}) == 'a &amp; b'

    def test_escapes_double_quote(self) -> None:
        assert render('{{val}}', {'val': 'say "hi"'}) == 'say &quot;hi&quot;'

    def test_escapes_single_quote(self) -> None:
        assert render('{{val}}', {'val': "it's"}) == 'it&#x27;s'

    def test_escapes_backtick(self) -> None:
        assert render('{{val}}', {'val': '`code`'}) == '&#x60;code&#x60;'

    def test_escapes_equals(self) -> None:
        assert render('{{val}}', {'val': 'a=b'}) == 'a&#x3D;b'


class TestTripleStache:
    def test_no_escaping(self) -> None:
        assert render('{{{val}}}', {'val': '<b>bold</b>'}) == '<b>bold</b>'

    def test_ampersand_no_escaping(self) -> None:
        assert render('{{&val}}', {'val': '<b>bold</b>'}) == '<b>bold</b>'


class TestSafeString:
    def test_safe_string_not_escaped(self) -> None:
        assert render('{{val}}', {'val': SafeString('<b>safe</b>')}) == '<b>safe</b>'


class TestCompile:
    def test_compile_and_call(self) -> None:
        template = compile('Hello {{name}}!')
        assert template({'name': 'World'}) == 'Hello World!'

    def test_compile_reuse(self) -> None:
        template = compile('{{greeting}} {{name}}!')
        assert template({'greeting': 'Hi', 'name': 'Alice'}) == 'Hi Alice!'
        assert template({'greeting': 'Hey', 'name': 'Bob'}) == 'Hey Bob!'

    def test_compile_no_context(self) -> None:
        template = compile('Hello!')
        assert template() == 'Hello!'


class TestEscapedDelimiters:
    def test_escaped_mustache(self) -> None:
        result = render('\\{{name}}', {'name': 'World'})
        assert result == '{{name}}'


class TestComments:
    def test_short_comment_removed(self) -> None:
        assert render('a{{! comment }}b', {}) == 'ab'

    def test_long_comment_removed(self) -> None:
        assert render('a{{!-- long comment --}}b', {}) == 'ab'

    def test_comment_with_mustache_chars(self) -> None:
        assert render('a{{!-- {{ }} --}}b', {}) == 'ab'


class TestThisKeyword:
    def test_this_returns_context(self) -> None:
        assert render('{{this}}', 'hello') == 'hello'  # pyright: ignore[reportArgumentType]

    def test_dot_returns_context(self) -> None:
        assert render('{{.}}', 'hello') == 'hello'  # pyright: ignore[reportArgumentType]

    def test_this_dot_property(self) -> None:
        assert render('{{this.name}}', {'name': 'Alice'}) == 'Alice'


class TestRawBlocks:
    def test_raw_block_content(self) -> None:
        result = render('{{{{raw}}}}{{not processed}}{{{{/raw}}}}', {})
        assert result == '{{not processed}}'
