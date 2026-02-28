"""Tests for Handlebars security features."""

from __future__ import annotations

import pytest

from logfire.handlebars import render
from logfire.handlebars._compiler import MAX_DEPTH, MAX_OUTPUT_SIZE, Compiler
from logfire.handlebars._exceptions import HandlebarsRuntimeError
from logfire.handlebars._parser import parse
from logfire.handlebars._utils import BLOCKED_ATTRIBUTES, is_blocked_attribute


class TestBlockedAttributes:
    def test_dunder_class_blocked(self) -> None:
        assert is_blocked_attribute('__class__')

    def test_dunder_dict_blocked(self) -> None:
        assert is_blocked_attribute('__dict__')

    def test_dunder_import_blocked(self) -> None:
        assert is_blocked_attribute('__import__')

    def test_dunder_globals_blocked(self) -> None:
        assert is_blocked_attribute('__globals__')

    def test_dunder_subclasses_blocked(self) -> None:
        assert is_blocked_attribute('__subclasses__')

    def test_constructor_blocked(self) -> None:
        assert is_blocked_attribute('constructor')

    def test_normal_attribute_not_blocked(self) -> None:
        assert not is_blocked_attribute('name')

    def test_all_blocked_attributes_in_set(self) -> None:
        for attr in BLOCKED_ATTRIBUTES:
            assert is_blocked_attribute(attr)

    def test_any_dunder_blocked(self) -> None:
        assert is_blocked_attribute('__anything__')

    def test_blocked_in_template_returns_empty(self) -> None:
        class Obj:
            name = 'test'

        obj = Obj()
        # __class__ should not be accessible
        result = render('{{obj.__class__}}', {'obj': obj})
        assert result == ''

    def test_blocked_nested_path(self) -> None:
        result = render('{{obj.__dict__}}', {'obj': {'__dict__': 'secret'}})
        assert result == ''


class TestHTMLEscaping:
    def test_xss_prevention(self) -> None:
        result = render('{{input}}', {'input': '<script>alert("xss")</script>'})
        assert '<script>' not in result
        assert '&lt;script&gt;' in result

    def test_all_special_chars_escaped(self) -> None:
        for char in ['&', '<', '>', '"', "'", '`', '=']:
            result = render('{{val}}', {'val': char})
            assert result != char, f'{char!r} was not escaped'


class TestMaxDepth:
    def test_max_depth_constant(self) -> None:
        assert MAX_DEPTH == 100

    def test_excessive_nesting_raises(self) -> None:
        from logfire.handlebars._helpers import get_default_helpers

        helpers = get_default_helpers()
        # Each _render_program call increments depth.
        # Top-level render -> depth 1
        # #if block body (via _call_block_helper -> fn -> _render_program) -> depth 2
        # nested #if block body -> depth 3
        # With max_depth=2, the third call exceeds the limit.
        compiler = Compiler(helpers=helpers, max_depth=2)
        template = '{{#if a}}{{#if b}}deep{{/if}}{{/if}}'
        program = parse(template)
        with pytest.raises(HandlebarsRuntimeError, match='Maximum nesting depth'):
            compiler.render(program, {'a': True, 'b': True})

    def test_within_depth_limit(self) -> None:
        from logfire.handlebars._helpers import get_default_helpers

        helpers = get_default_helpers()
        compiler = Compiler(helpers=helpers, max_depth=10)
        template = '{{#if a}}{{#if b}}ok{{/if}}{{/if}}'
        program = parse(template)
        result = compiler.render(program, {'a': True, 'b': True})
        assert result == 'ok'


class TestMaxOutputSize:
    def test_max_output_constant(self) -> None:
        assert MAX_OUTPUT_SIZE == 10 * 1024 * 1024

    def test_output_exceeds_max_raises(self) -> None:
        compiler = Compiler(max_output_size=10)
        template = '{{value}}'
        program = parse(template)
        with pytest.raises(HandlebarsRuntimeError, match='Output size exceeds maximum'):
            compiler.render(program, {'value': 'x' * 20})

    def test_output_within_limit(self) -> None:
        compiler = Compiler(max_output_size=100)
        template = '{{value}}'
        program = parse(template)
        result = compiler.render(program, {'value': 'short'})
        assert result == 'short'
