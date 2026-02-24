"""Tests for Handlebars subexpressions."""

from __future__ import annotations

import pytest

from logfire.handlebars import render
from logfire.handlebars._exceptions import HandlebarsRuntimeError


class TestSubexpressions:
    def test_nested_helper_call(self) -> None:
        result = render('{{uppercase (lowercase "HELLO")}}', {})
        assert result == 'HELLO'

    def test_subexpression_as_if_condition(self) -> None:
        result = render('{{#if (eq a b)}}same{{else}}diff{{/if}}', {'a': 1, 'b': 1})
        assert result == 'same'

    def test_subexpression_as_if_condition_false(self) -> None:
        result = render('{{#if (eq a b)}}same{{else}}diff{{/if}}', {'a': 1, 'b': 2})
        assert result == 'diff'

    def test_subexpression_with_gt(self) -> None:
        result = render('{{#if (gt a b)}}greater{{else}}not{{/if}}', {'a': 5, 'b': 3})
        assert result == 'greater'

    def test_nested_subexpressions(self) -> None:
        result = render('{{#if (and (eq a 1) (eq b 2))}}yes{{else}}no{{/if}}', {'a': 1, 'b': 2})
        assert result == 'yes'

    def test_unknown_helper_in_subexpression(self) -> None:
        with pytest.raises(HandlebarsRuntimeError, match='Unknown helper'):
            render('{{#if (nonexistent val)}}yes{{/if}}', {'val': True})

    def test_subexpression_or(self) -> None:
        result = render('{{#if (or a b)}}yes{{else}}no{{/if}}', {'a': False, 'b': True})
        assert result == 'yes'

    def test_subexpression_not(self) -> None:
        result = render('{{#if (not val)}}yes{{else}}no{{/if}}', {'val': False})
        assert result == 'yes'
