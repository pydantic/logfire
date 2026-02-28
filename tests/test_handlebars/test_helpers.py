"""Tests for built-in Handlebars helpers."""

from __future__ import annotations

from logfire.handlebars import render


class TestIfHelper:
    def test_truthy_string(self) -> None:
        assert render('{{#if name}}yes{{/if}}', {'name': 'Alice'}) == 'yes'

    def test_falsy_empty_string(self) -> None:
        assert render('{{#if name}}yes{{/if}}', {'name': ''}) == ''

    def test_falsy_zero(self) -> None:
        assert render('{{#if val}}yes{{/if}}', {'val': 0}) == ''

    def test_falsy_none(self) -> None:
        assert render('{{#if val}}yes{{/if}}', {'val': None}) == ''

    def test_falsy_empty_list(self) -> None:
        assert render('{{#if items}}yes{{/if}}', {'items': []}) == ''

    def test_falsy_false(self) -> None:
        assert render('{{#if val}}yes{{/if}}', {'val': False}) == ''

    def test_truthy_nonempty_list(self) -> None:
        assert render('{{#if items}}yes{{/if}}', {'items': [1]}) == 'yes'

    def test_truthy_number(self) -> None:
        assert render('{{#if val}}yes{{/if}}', {'val': 42}) == 'yes'

    def test_if_else(self) -> None:
        assert render('{{#if val}}yes{{else}}no{{/if}}', {'val': True}) == 'yes'
        assert render('{{#if val}}yes{{else}}no{{/if}}', {'val': False}) == 'no'

    def test_if_else_if(self) -> None:
        template = '{{#if a}}A{{else if b}}B{{else}}C{{/if}}'
        assert render(template, {'a': True, 'b': True}) == 'A'
        assert render(template, {'a': False, 'b': True}) == 'B'
        assert render(template, {'a': False, 'b': False}) == 'C'


class TestUnlessHelper:
    def test_unless_falsy(self) -> None:
        assert render('{{#unless val}}shown{{/unless}}', {'val': False}) == 'shown'

    def test_unless_truthy(self) -> None:
        assert render('{{#unless val}}shown{{/unless}}', {'val': True}) == ''

    def test_unless_with_else(self) -> None:
        assert render('{{#unless val}}no{{else}}yes{{/unless}}', {'val': True}) == 'yes'


class TestEachHelper:
    def test_each_array(self) -> None:
        result = render('{{#each items}}{{this}} {{/each}}', {'items': ['a', 'b', 'c']})
        assert result == 'a b c '

    def test_each_array_index(self) -> None:
        result = render('{{#each items}}{{@index}}:{{this}} {{/each}}', {'items': ['x', 'y']})
        assert result == '0:x 1:y '

    def test_each_array_first_last(self) -> None:
        template = '{{#each items}}{{#if @first}}[{{/if}}{{this}}{{#if @last}}]{{/if}}{{/each}}'
        result = render(template, {'items': ['a', 'b', 'c']})
        assert result == '[abc]'

    def test_each_object(self) -> None:
        result = render('{{#each obj}}{{@key}}={{this}} {{/each}}', {'obj': {'x': 1, 'y': 2}})
        assert result == 'x=1 y=2 '

    def test_each_object_key(self) -> None:
        result = render('{{#each obj}}{{@key}} {{/each}}', {'obj': {'a': 1, 'b': 2}})
        assert result == 'a b '

    def test_each_empty_array_else(self) -> None:
        result = render('{{#each items}}{{this}}{{else}}empty{{/each}}', {'items': []})
        assert result == 'empty'

    def test_each_none_else(self) -> None:
        result = render('{{#each items}}{{this}}{{else}}empty{{/each}}', {'items': None})
        assert result == 'empty'

    def test_each_with_block_params(self) -> None:
        template = '{{#each items as |item idx|}}{{idx}}:{{item}} {{/each}}'
        result = render(template, {'items': ['a', 'b']})
        assert result == '0:a 1:b '


class TestWithHelper:
    def test_with_changes_context(self) -> None:
        result = render('{{#with person}}{{name}}{{/with}}', {'person': {'name': 'Alice'}})
        assert result == 'Alice'

    def test_with_else_on_falsy(self) -> None:
        result = render('{{#with person}}{{name}}{{else}}no person{{/with}}', {'person': None})
        assert result == 'no person'

    def test_with_nested(self) -> None:
        ctx = {'person': {'address': {'city': 'NYC'}}}
        result = render('{{#with person}}{{#with address}}{{city}}{{/with}}{{/with}}', ctx)
        assert result == 'NYC'


class TestLookupHelper:
    def test_lookup_dict(self) -> None:
        result = render('{{lookup obj key}}', {'obj': {'x': 'found'}, 'key': 'x'})
        assert result == 'found'

    def test_lookup_array(self) -> None:
        result = render('{{lookup items 1}}', {'items': ['a', 'b', 'c']})
        assert result == 'b'

    def test_lookup_missing(self) -> None:
        result = render('{{lookup obj "missing"}}', {'obj': {'x': 1}})
        assert result == ''


class TestCustomHelpers:
    def test_uppercase(self) -> None:
        assert render('{{uppercase name}}', {'name': 'hello'}) == 'HELLO'

    def test_lowercase(self) -> None:
        assert render('{{lowercase name}}', {'name': 'HELLO'}) == 'hello'

    def test_trim(self) -> None:
        assert render('{{trim name}}', {'name': '  hello  '}) == 'hello'

    def test_join(self) -> None:
        result = render('{{join items ", "}}', {'items': ['a', 'b', 'c']})
        assert result == 'a, b, c'

    def test_join_default_separator(self) -> None:
        result = render('{{join items}}', {'items': ['a', 'b']})
        assert result == 'a,b'

    def test_truncate(self) -> None:
        result = render('{{truncate name 5}}', {'name': 'Hello World'})
        assert result == 'Hello'

    def test_truncate_short_enough(self) -> None:
        result = render('{{truncate name 20}}', {'name': 'Hello'})
        assert result == 'Hello'

    def test_json(self) -> None:
        result = render('{{json obj}}', {'obj': {'a': 1}})
        assert result == '{&quot;a&quot;: 1}'

    def test_eq(self) -> None:
        assert render('{{eq 1 1}}', {}) == 'true'
        assert render('{{eq 1 2}}', {}) == 'false'

    def test_ne(self) -> None:
        assert render('{{ne 1 2}}', {}) == 'true'
        assert render('{{ne 1 1}}', {}) == 'false'

    def test_gt(self) -> None:
        assert render('{{gt 2 1}}', {}) == 'true'
        assert render('{{gt 1 2}}', {}) == 'false'

    def test_gte(self) -> None:
        assert render('{{gte 2 2}}', {}) == 'true'

    def test_lt(self) -> None:
        assert render('{{lt 1 2}}', {}) == 'true'

    def test_lte(self) -> None:
        assert render('{{lte 2 2}}', {}) == 'true'

    def test_and(self) -> None:
        assert render('{{#if (and a b)}}yes{{/if}}', {'a': True, 'b': True}) == 'yes'
        assert render('{{#if (and a b)}}yes{{/if}}', {'a': True, 'b': False}) == ''

    def test_or(self) -> None:
        assert render('{{#if (or a b)}}yes{{/if}}', {'a': False, 'b': True}) == 'yes'
        assert render('{{#if (or a b)}}yes{{/if}}', {'a': False, 'b': False}) == ''

    def test_not(self) -> None:
        assert render('{{#if (not val)}}yes{{/if}}', {'val': False}) == 'yes'
        assert render('{{#if (not val)}}yes{{/if}}', {'val': True}) == ''

    def test_default(self) -> None:
        assert render('{{default name "unknown"}}', {'name': ''}) == 'unknown'
        assert render('{{default name "unknown"}}', {'name': 'Alice'}) == 'Alice'
