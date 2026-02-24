"""Tests for Handlebars whitespace control."""

from __future__ import annotations

from logfire.handlebars import render


class TestStripBefore:
    def test_strip_before_expression(self) -> None:
        result = render('Hello   {{~name}}', {'name': 'World'})
        assert result == 'HelloWorld'

    def test_strip_before_with_newline(self) -> None:
        result = render('Hello\n  {{~name}}', {'name': 'World'})
        assert result == 'HelloWorld'


class TestStripAfter:
    def test_strip_after_expression(self) -> None:
        result = render('{{name~}}   World', {'name': 'Hello'})
        assert result == 'HelloWorld'

    def test_strip_after_with_newline(self) -> None:
        result = render('{{name~}}\n  World', {'name': 'Hello'})
        assert result == 'HelloWorld'


class TestStripBoth:
    def test_strip_both_sides(self) -> None:
        result = render('Hello   {{~name~}}   World', {'name': ', '})
        assert result == 'Hello, World'


class TestBlockWhitespace:
    def test_if_block_strip(self) -> None:
        template = 'before {{~#if val~}} middle {{~/if~}} after'
        result = render(template, {'val': True})
        assert result == 'beforemiddleafter'

    def test_each_block_strip(self) -> None:
        template = 'start {{~#each items~}} {{this}} {{~/each~}} end'
        result = render(template, {'items': ['a', 'b']})
        # All ~ markers strip adjacent whitespace; inner content whitespace is also stripped
        assert result == 'startabend'


class TestCommentWhitespace:
    def test_comment_removed_preserves_whitespace(self) -> None:
        # Comments are removed but surrounding whitespace is preserved
        result = render('Hello {{! comment }} World', {})
        assert result == 'Hello  World'

    def test_comment_inline(self) -> None:
        # Comments are removed inline, adjacent text stays
        result = render('a{{! comment }}b', {})
        assert result == 'ab'
